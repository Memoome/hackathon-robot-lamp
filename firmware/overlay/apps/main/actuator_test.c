#include "actuator_test.h"
#if defined(CONFIG_OFFLINE_AUDIO_TEST) && CONFIG_OFFLINE_AUDIO_TEST
#include "qm.h"
#include "qm_cli.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <stdint.h>
#include "esp_random.h"
#include <stdlib.h>
#include <string.h>

/* Confirmed VCC/GND/IN module; its reference specifies active-high PWM. */
#define ACTUATOR_MOTOR_DRIVER_PRESENT 1
#define MOTOR_GPIO GPIO_NUM_13
#define TAG "act_test"
static const gpio_num_t pins[4] = {GPIO_NUM_12, GPIO_NUM_10, GPIO_NUM_11, GPIO_NUM_15};
static const ledc_channel_t channels[4] = {LEDC_CHANNEL_4, LEDC_CHANNEL_5, LEDC_CHANNEL_3, LEDC_CHANNEL_2};
static SemaphoreHandle_t lock;
static int64_t deadlines[4];
static int64_t motor_deadline;
static int motor_initialized;
static int ready;
static int angles[3]={-1,-1,-1};
static int64_t arm_lease;
static uint32_t arm_session;
static unsigned live_pulse[4], live_lo[4], live_hi[4], live_speed[4];
static int live_dir[4], live_hold[4];
static int64_t live_motion_until[4],live_fraction[4],live_last_tick;
static int base_spinning;
static unsigned base_neutral=1500;
static int64_t base_stop_until;


static void release_locked(int index)
{
    ledc_stop(LEDC_LOW_SPEED_MODE, channels[index], 0);
    deadlines[index] = 0;
}

static void release_all_locked(void)
{
    for (int i = 0; i < 4; i++) release_locked(i);
    for(int i=0;i<4;i++){live_pulse[i]=0;live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;}
    base_spinning=0;base_stop_until=0;
    if (motor_initialized) ledc_stop(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6,0);
    motor_deadline=0;
    arm_lease=0;
    for(int i=0;i<3;i++) angles[i]=-1;
}

static int bounded(const char *s, unsigned lo, unsigned hi, unsigned *out)
{
    if (!s || !*s || strlen(s) > 4) return 0;
    for (const char *p=s; *p; p++) if (*p<'0' || *p>'9') return 0;
    unsigned long n = strtoul(s, NULL, 10);
    if (n<lo || n>hi) return 0;
    *out=(unsigned)n;
    return 1;
}

static void status_locked(void)
{
    QM_LOGI(TAG, "ACT_STATUS version=1 ready=%d mg_gpio=12 sg_gpio=10 motor_gpio=13 motor_driver=1 mg_active=%d sg_active=%d motor_active=%d", ready, deadlines[0]!=0, deadlines[1]!=0,motor_deadline!=0);
}

static void command(char *out, int out_len, int argc, char **argv)
{
    (void)out; (void)out_len;
    if (!ready) { QM_LOGW(TAG, "ACT_ERROR not_ready"); return; }
    xSemaphoreTake(lock, portMAX_DELAY);
    if (argc==2 && !strcmp(argv[1],"status")) {
        status_locked();
    } else if (argc==2 && !strcmp(argv[1],"stop")) {
        release_all_locked();
        QM_LOGI(TAG, "ACT_OK action=stop all_signals=OFF");
    } else if (argc==4 && !strcmp(argv[1],"motor")) {
        unsigned percent,ms;
        if (!bounded(argv[2],0,100,&percent) || !bounded(argv[3],100,500,&ms)) {
            QM_LOGW(TAG,"ACT_ERROR invalid_range duty=0..100 duration_ms=100..500");
        } else {
            release_all_locked();
            esp_err_t err=ESP_OK;
            if(percent) {
                uint32_t duty=(percent*1023u+50u)/100u;
                err=ledc_set_duty(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6,duty);
                if(err==ESP_OK) err=ledc_update_duty(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6);
                if(err==ESP_OK) motor_deadline=esp_timer_get_time()+(int64_t)ms*1000;
            }
            if(err==ESP_OK) QM_LOGI(TAG,"ACT_OK action=motor duty=%u duration_ms=%u",percent,ms);
            else {release_all_locked(); QM_LOGE(TAG,"ACT_ERROR pwm rc=%d",err);}
        }
    } else if (argc==5 && !strcmp(argv[1],"servo")) {
        unsigned pin, pulse, ms;
        if (!bounded(argv[2],10,12,&pin) || (pin!=10 && pin!=12) ||
            !bounded(argv[3],1300,1700,&pulse) || !bounded(argv[4],100,600,&ms)) {
            QM_LOGW(TAG, "ACT_ERROR invalid_range gpio=10_or_12 pulse_us=1300..1700 duration_ms=100..600");
        } else {
            int index = pin==12 ? 0 : 1;
            release_all_locked(); /* Only one servo draws drive current at once. */
            uint32_t duty = (pulse * (1u << 14) + 10000u) / 20000u;
            esp_err_t err = ledc_set_duty(LEDC_LOW_SPEED_MODE,channels[index],duty);
            if (err==ESP_OK) err=ledc_update_duty(LEDC_LOW_SPEED_MODE,channels[index]);
            if (err==ESP_OK) {
                deadlines[index]=esp_timer_get_time()+(int64_t)ms*1000;
                QM_LOGI(TAG, "ACT_OK action=servo gpio=%u pulse_us=%u duration_ms=%u",pin,pulse,ms);
            } else {
                release_all_locked();
                QM_LOGE(TAG, "ACT_ERROR pwm rc=%d",err);
            }
        }
    } else {
        QM_LOGW(TAG, "ACT_ERROR usage=act_test_status_or_stop_or_servo_GPIO_PULSE_MS");
    }
    xSemaphoreGive(lock);
}


/* Arm signals are off at boot. Angles are command estimates, never feedback.
 * 1000..2000us is a conservative initial scale; UI limits default to 60..120.
 * A 5-second host lease bounds holding if the PC disappears. */
static void arm_status(void)
{
    QM_LOGI(TAG,"ARM_STATUS version=1 session=%lu gpio=12,10,11 angles=%d,%d,%d active=%d,%d,%d lease=%d",
        (unsigned long)arm_session,angles[0],angles[1],angles[2],
        deadlines[0]!=0,deadlines[1]!=0,deadlines[2]!=0,arm_lease!=0);
}
static void arm_command(char *out,int out_len,int argc,char **argv)
{
    (void)out;(void)out_len;
    if(!ready){QM_LOGW(TAG,"ARM_ERROR not_ready");return;}
    xSemaphoreTake(lock,portMAX_DELAY);
    if(argc==2 && !strcmp(argv[1],"status")) arm_status();
    else if(argc==2 && !strcmp(argv[1],"stop")) {
        release_all_locked(); QM_LOGI(TAG,"ARM_OK stop signals=OFF");
    } else if(argc==2 && !strcmp(argv[1],"ping")) {
        if(arm_lease) arm_lease=esp_timer_get_time()+5000000;
        arm_status();
    } else if(argc==7 && !strcmp(argv[1],"move")) {
        unsigned pin,angle,lo,hi,hold;
        if(!bounded(argv[2],10,12,&pin) || !bounded(argv[3],0,180,&angle) ||
           !bounded(argv[4],500,1500,&lo) || !bounded(argv[5],1500,2500,&hi) ||
           hi<=lo || !bounded(argv[6],0,1,&hold)) QM_LOGW(TAG,"ARM_ERROR invalid_range");
        else {
            int index=pin==12?0:pin==10?1:2;
            if(!hold) release_all_locked();
            else {if(motor_initialized)ledc_stop(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6,0);motor_deadline=0;}
            unsigned pulse=lo+((hi-lo)*angle+90)/180;
            uint32_t duty=(pulse*(1u<<14)+10000)/20000;
            esp_err_t err=ledc_set_duty(LEDC_LOW_SPEED_MODE,channels[index],duty);
            if(err==ESP_OK)err=ledc_update_duty(LEDC_LOW_SPEED_MODE,channels[index]);
            if(err==ESP_OK){
                angles[index]=angle;
                deadlines[index]=hold?-1:esp_timer_get_time()+700000;
                arm_lease=hold?esp_timer_get_time()+5000000:0;
                QM_LOGI(TAG,"ARM_OK move gpio=%u angle=%u pulse_us=%u hold=%u",pin,angle,pulse,hold);
            } else {release_all_locked();QM_LOGW(TAG,"ARM_ERROR pwm rc=%d",err);}
        }
    } else QM_LOGW(TAG,"ARM_ERROR usage=status_stop_ping_or_move_GPIO_ANGLE_LOW_US_HIGH_US_HOLD");
    xSemaphoreGive(lock);
}
static const struct qm_cli_command arm_cli={"arm_test","Three position servos GPIO12,10,11; command estimates and watchdog",arm_command};

static const struct qm_cli_command cli = {"act_test", "Bounded servo tests: GPIO12 MG90S, GPIO10 SG90; PWM motor module GPIO13", command};


static esp_err_t live_write(int i,unsigned pulse)
{
    uint32_t duty=(pulse*(1u<<14)+10000)/20000;
    esp_err_t err=ledc_set_duty(LEDC_LOW_SPEED_MODE,channels[i],duty);
    if(err==ESP_OK)err=ledc_update_duty(LEDC_LOW_SPEED_MODE,channels[i]);
    if(err==ESP_OK)live_pulse[i]=pulse;
    return err;
}
static void live_freeze(int64_t now)
{
    for(int i=0;i<4;i++){
        live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;
        if(deadlines[i] && !live_hold[i])deadlines[i]=now+700000;
    }
    if(base_spinning){
        if(live_write(3,base_neutral)!=ESP_OK){release_locked(3);live_pulse[3]=0;}
        base_spinning=0;base_stop_until=now+250000;
    }
}
static void live_status(void)
{
    QM_LOGI(TAG,"LIVE_STATUS version=1 session=%lu gpio=12,10,11,15 pulse=%u,%u,%u,%u active=%d,%d,%d,%d moving=%d,%d,%d,%d base_spin=%d lease=%d",
        (unsigned long)arm_session,live_pulse[0],live_pulse[1],live_pulse[2],live_pulse[3],
        deadlines[0]!=0,deadlines[1]!=0,deadlines[2]!=0,deadlines[3]!=0,
        live_dir[0]!=0,live_dir[1]!=0,live_dir[2]!=0,live_dir[3]!=0,base_spinning,arm_lease!=0);
}
static int live_index(unsigned pin){return pin==12?0:pin==10?1:pin==11?2:pin==15?3:-1;}

static int live_glide(unsigned a,unsigned b,unsigned c,unsigned speed,int64_t now)
{
    unsigned goals[3]={a,b,c};
    for(int i=0;i<3;i++)if(!deadlines[i] || live_pulse[i]<500 || live_pulse[i]>2500)return 0;
    for(int i=0;i<3;i++){
        int direction=goals[i]>live_pulse[i]?1:goals[i]<live_pulse[i]?-1:0;
        if(direction!=live_dir[i])live_fraction[i]=0;
        live_dir[i]=direction;live_speed[i]=speed;
        live_lo[i]=goals[i]<live_pulse[i]?goals[i]:live_pulse[i];
        live_hi[i]=goals[i]>live_pulse[i]?goals[i]:live_pulse[i];
        live_motion_until[i]=direction?now+400000:0;live_hold[i]=1;deadlines[i]=-1;
    }
    arm_lease=now+5000000;
    return 1;
}

static void live_command(char *out,int out_len,int argc,char **argv)
{
    (void)out;(void)out_len;
    if(!ready){QM_LOGW(TAG,"LIVE_ERROR not_ready");return;}
    xSemaphoreTake(lock,portMAX_DELAY);
    unsigned pin,pulse,mode,direction,speed,lo,hi,neutral;
    int64_t now=esp_timer_get_time();
    if(argc==2 && !strcmp(argv[1],"status"))live_status();
    else if(argc==2 && !strcmp(argv[1],"ping")){
        if(arm_lease){arm_lease=now+5000000;}live_status();
    } else if(argc==2 && !strcmp(argv[1],"freeze")){
        live_freeze(now);if(arm_lease)arm_lease=now+5000000;live_status();
    } else if(argc==2 && !strcmp(argv[1],"off")){
        /* Positions release; a spinning base gets a brief neutral stop command. */
        int was_spinning=base_spinning;release_all_locked();
        if(was_spinning && live_write(3,base_neutral)==ESP_OK){deadlines[3]=-1;base_stop_until=now+250000;}
        live_status();
    } else if(argc==6 && !strcmp(argv[1],"glide") && bounded(argv[2],500,2500,&pulse) &&
              bounded(argv[3],500,2500,&lo) && bounded(argv[4],500,2500,&hi) && bounded(argv[5],10,600,&speed)){
        if(live_glide(pulse,lo,hi,speed,now))live_status();else QM_LOGW(TAG,"LIVE_ERROR engage_first");
    } else if(argc==9 && !strcmp(argv[1],"glide_scene") && bounded(argv[2],500,2500,&pulse) &&
              bounded(argv[3],500,2500,&lo) && bounded(argv[4],500,2500,&hi) && bounded(argv[5],10,600,&speed) &&
              bounded(argv[6],500,2500,&pin) && bounded(argv[7],100,2000,&mode) && bounded(argv[8],1400,1600,&neutral)){
        if(!live_glide(pulse,lo,hi,speed,now))QM_LOGW(TAG,"LIVE_ERROR engage_first");
        else{
            base_neutral=neutral;live_dir[3]=0;live_fraction[3]=0;
            if(live_write(3,pin)==ESP_OK){
                live_hold[3]=0;deadlines[3]=-1;base_spinning=pin!=neutral;
                live_motion_until[3]=now+(int64_t)mode*1000;base_stop_until=base_spinning?0:now+250000;
                live_status();
            }else{release_all_locked();QM_LOGW(TAG,"LIVE_ERROR glide_base_pwm");}
        }
    } else if(argc==5 && !strcmp(argv[1],"pose") && bounded(argv[2],500,2500,&pulse) &&
              bounded(argv[3],500,2500,&lo) && bounded(argv[4],500,2500,&hi)){
        /* Update the three position channels under one lock; leave base timing alone. */
        unsigned values[3]={pulse,lo,hi};int failed=0;
        for(int i=0;i<3;i++){
            live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;
            if(live_write(i,values[i])!=ESP_OK){failed=1;break;}
            live_hold[i]=1;deadlines[i]=-1;
        }
        if(failed){release_all_locked();QM_LOGW(TAG,"LIVE_ERROR pose_pwm");}
        else{arm_lease=now+5000000;live_status();}
    } else if(argc==8 && !strcmp(argv[1],"scene") && bounded(argv[2],500,2500,&pulse) &&
              bounded(argv[3],500,2500,&lo) && bounded(argv[4],500,2500,&hi) &&
              bounded(argv[5],500,2500,&pin) && bounded(argv[6],100,2000,&speed) && bounded(argv[7],1400,1600,&neutral)){
        unsigned values[3]={pulse,lo,hi};int failed=0;
        for(int i=0;i<3;i++){
            live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;
            if(live_write(i,values[i])!=ESP_OK){failed=1;break;}
            live_hold[i]=1;deadlines[i]=-1;
        }
        base_neutral=neutral;live_dir[3]=0;live_fraction[3]=0;
        if(!failed && live_write(3,pin)==ESP_OK){
            live_hold[3]=0;deadlines[3]=-1;base_spinning=pin!=neutral;
            live_motion_until[3]=now+(int64_t)speed*1000;
            base_stop_until=base_spinning?0:now+250000;
            arm_lease=now+5000000;live_status();
        }else{release_all_locked();QM_LOGW(TAG,"LIVE_ERROR scene_pwm");}
    } else if(argc==5 && !strcmp(argv[1],"engage") && bounded(argv[2],10,15,&pin) && live_index(pin)>=0 &&
              bounded(argv[3],500,2500,&pulse) && bounded(argv[4],0,1,&mode)){
        int i=live_index(pin);
        if(mode==0)release_all_locked();else live_freeze(now);
        if(live_write(i,pulse)==ESP_OK){
            live_hold[i]=mode;deadlines[i]=mode?-1:now+5000000;arm_lease=now+5000000;
            if(i==3){base_spinning=0;base_stop_until=0;}
            live_status();
        }else{release_all_locked();QM_LOGW(TAG,"LIVE_ERROR pwm");}
    } else if(argc==8 && !strcmp(argv[1],"jog") && bounded(argv[2],10,15,&pin) && live_index(pin)>=0 &&
              bounded(argv[3],0,1,&direction) && bounded(argv[4],10,600,&speed) &&
              bounded(argv[5],500,2500,&lo) && bounded(argv[6],500,2500,&hi) && lo<hi && bounded(argv[7],0,1,&mode)){
        int i=live_index(pin);
        if(!live_pulse[i] || live_pulse[i]<lo || live_pulse[i]>hi || (i==3 && base_spinning))QM_LOGW(TAG,"LIVE_ERROR engage_first");
        else{
            if(mode==0){
                for(int j=0;j<4;j++)if(j!=i){release_locked(j);live_pulse[j]=0;live_dir[j]=0;live_motion_until[j]=0;}
                base_spinning=0;base_stop_until=0;
            }
            live_dir[i]=direction?1:-1;live_speed[i]=speed;live_lo[i]=lo;live_hi[i]=hi;live_hold[i]=mode;
            live_motion_until[i]=now+400000;deadlines[i]=-1;arm_lease=now+5000000;live_status();
        }
    } else if(argc==5 && !strcmp(argv[1],"base") && bounded(argv[2],0,2,&direction) &&
              bounded(argv[3],0,1100,&speed) && bounded(argv[4],1400,1600,&neutral)){
        /* direction 0=stop,1=lower pulse,2=higher pulse; offset is not RPM. */
        base_neutral=neutral;live_dir[3]=0;live_motion_until[3]=0;live_fraction[3]=0;
        pulse=direction==1?neutral-speed:direction==2?neutral+speed:neutral;
        if(pulse<500){pulse=500;}if(pulse>2500){pulse=2500;}
        if(live_write(3,pulse)==ESP_OK){
            live_hold[3]=0;deadlines[3]=-1;base_spinning=direction!=0 && speed!=0;
            base_stop_until=base_spinning?0:now+250000;
            live_motion_until[3]=base_spinning?now+400000:0;arm_lease=now+5000000;live_status();
        }else{release_all_locked();QM_LOGW(TAG,"LIVE_ERROR pwm");}
    } else QM_LOGW(TAG,"LIVE_ERROR invalid_command_or_range");
    xSemaphoreGive(lock);
}
static const struct qm_cli_command live_cli={"arm_live","Four servo manual hold-to-jog; base signal GPIO15",live_command};

static void live_tick(int64_t now)
{
    int64_t elapsed=live_last_tick?now-live_last_tick:0;live_last_tick=now;
    /* If the task was delayed, stop rather than jumping through missed motion. */
    if(elapsed>100000)live_freeze(now);
    if(base_spinning && now>=live_motion_until[3]){
        /* End the base turn without interrupting the position-joint ramps. */
        live_dir[3]=0;live_motion_until[3]=0;live_fraction[3]=0;
        if(live_write(3,base_neutral)!=ESP_OK){release_locked(3);live_pulse[3]=0;}
        base_spinning=0;base_stop_until=now+250000;
    }
    if(base_stop_until && now>=base_stop_until){release_locked(3);live_pulse[3]=0;base_stop_until=0;}
    for(int i=0;i<4;i++){
        if(!live_dir[i])continue;
        if(now>=live_motion_until[i]){
            live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;
            if(!live_hold[i])deadlines[i]=now+700000;
            continue;
        }
        live_fraction[i]+=(int64_t)live_speed[i]*elapsed;
        unsigned step=live_fraction[i]/1000000;live_fraction[i]%=1000000;
        if(step>10){step=10;} /* No catch-up jumps after scheduler jitter. */
        if(!step)continue;
        int target=(int)live_pulse[i]+live_dir[i]*(int)step;
        if(target<live_lo[i]){target=live_lo[i];}if(target>live_hi[i]){target=live_hi[i];}
        if(live_write(i,(unsigned)target)!=ESP_OK){release_all_locked();break;}
        if(target==live_lo[i] || target==live_hi[i]){
            live_dir[i]=0;live_motion_until[i]=0;live_fraction[i]=0;
            if(!live_hold[i])deadlines[i]=now+700000;
        }
    }
}

static void watchdog(void *arg)
{
    (void)arg;
    for (;;) {
        xSemaphoreTake(lock,portMAX_DELAY);
        int64_t now=esp_timer_get_time();
        live_tick(now);
        for (int i=0;i<4;i++) {
            if (deadlines[i]>0 && now>=deadlines[i]) {
                release_locked(i);live_pulse[i]=0;
                QM_LOGI(TAG,"ACT_OFF gpio=%d reason=timeout",pins[i]);
            }
        }
        if(arm_lease && now>=arm_lease){release_all_locked();QM_LOGW(TAG,"ARM_OFF reason=host_timeout");}
        if(motor_deadline && now>=motor_deadline) {
            ledc_stop(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6,0);
            motor_deadline=0;
            QM_LOGI(TAG,"ACT_OFF gpio=13 reason=timeout");
        }
        xSemaphoreGive(lock);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

esp_err_t actuator_test_init(void)
{
    /* Active-high module input starts low; no test runs on boot. */
    gpio_config_t motor = {.pin_bit_mask=1ULL<<MOTOR_GPIO, .mode=GPIO_MODE_INPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE, .pull_down_en=GPIO_PULLDOWN_ENABLE,
        .intr_type=GPIO_INTR_DISABLE};
    esp_err_t err=gpio_config(&motor);
    if (err!=ESP_OK) return err;
    lock=xSemaphoreCreateMutex();
    if (!lock) return ESP_ERR_NO_MEM;
    ledc_timer_config_t timer = {.speed_mode=LEDC_LOW_SPEED_MODE,
        .duty_resolution=LEDC_TIMER_14_BIT, .timer_num=LEDC_TIMER_2,
        .freq_hz=50, .clk_cfg=LEDC_AUTO_CLK};
    err=ledc_timer_config(&timer);
    if (err!=ESP_OK) return err;
    for (int i=0;i<4;i++) {
        ledc_channel_config_t channel = {.gpio_num=pins[i], .speed_mode=LEDC_LOW_SPEED_MODE,
            .channel=channels[i], .intr_type=LEDC_INTR_DISABLE,
            .timer_sel=LEDC_TIMER_2, .duty=0, .hpoint=0};
        err=ledc_channel_config(&channel);
        if (err!=ESP_OK) { for(int j=0;j<i;j++) release_locked(j); return err; }
        release_locked(i);
    }
    ledc_timer_config_t motor_timer={.speed_mode=LEDC_LOW_SPEED_MODE,
        .duty_resolution=LEDC_TIMER_10_BIT,.timer_num=LEDC_TIMER_3,
        .freq_hz=1000,.clk_cfg=LEDC_AUTO_CLK};
    err=ledc_timer_config(&motor_timer);
    if(err!=ESP_OK) return err;
    ledc_channel_config_t motor_channel={.gpio_num=MOTOR_GPIO,
        .speed_mode=LEDC_LOW_SPEED_MODE,.channel=LEDC_CHANNEL_6,
        .intr_type=LEDC_INTR_DISABLE,.timer_sel=LEDC_TIMER_3,.duty=0,.hpoint=0};
    err=ledc_channel_config(&motor_channel);
    if(err!=ESP_OK) return err;
    motor_initialized=1;
    ledc_stop(LEDC_LOW_SPEED_MODE,LEDC_CHANNEL_6,0);
    if (xTaskCreate(watchdog,"act_watchdog",3072,NULL,6,NULL)!=pdPASS) return ESP_ERR_NO_MEM;
    if (qm_cli_register_command(&cli)!=QM_EOK) return ESP_FAIL;
    if(qm_cli_register_command(&arm_cli)!=QM_EOK)return ESP_FAIL;
    if(qm_cli_register_command(&live_cli)!=QM_EOK)return ESP_FAIL;
    arm_session=esp_random();
    ready=1;
    QM_LOGI(TAG,"LIVE_READY version=1 gpio=12,10,11,15 boot_signals=OFF jog_timeout_ms=400");
    QM_LOGI(TAG,"ARM_READY version=1 gpio=12,10,11 boot_signals=OFF");
    QM_LOGI(TAG,"ACT_READY version=1 mg_gpio=12 sg_gpio=10 motor_gpio=13 motor_driver=1 boot_signals=OFF max_ms=600");
    return ESP_OK;
}
#endif

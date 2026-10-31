#pragma once
#include <stddef.h>
void lamp_wireless_init(void);
int lamp_reply(const char *fmt,...);
void lamp_remote_arm(int argc,char **argv);
void lamp_remote_audio(int argc,char **argv);
void lamp_remote_led(int argc,char **argv);
int lamp_update_gate(int enable);

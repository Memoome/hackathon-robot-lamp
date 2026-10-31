"""Continuous, request-driven ESP32-S3 inference viewer. Inference runs on the board."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import queue
import re
import threading
import time
import uuid
import math
import hashlib
import camera_wire as wire
import posture

ROOT=Path(__file__).resolve().parents[1]
EDGES=((0,1),(0,2),(1,3),(2,4),(5,6),(5,7),(7,9),(6,8),(8,10),(5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16))

def orient(rgb,w,h,rotation):
    if rotation not in (0,90,180,270):raise ValueError('Invalid rotation')
    for _ in range(rotation//90):rgb,w,h=wire.rotate_rgb(rgb,w,h)
    return rgb,w,h

def validate_result(result,frame):
    rotation=frame['rotation']
    width,height=(320,240) if rotation in (90,270) else (240,320)
    if result.get('id')!=frame['id'] or result.get('rotation')!=rotation or (result.get('width'),result.get('height'))!=(width,height):
        raise ValueError('识别结果与画面不匹配')
    if not isinstance(result.get('people'),list) or len(result['people'])>5:raise ValueError('Invalid people list')
    if not isinstance(result.get('inference_ms'),(int,float)) or not math.isfinite(result['inference_ms']) or result['inference_ms']<0:raise ValueError('Invalid timing')
    for person in result['people']:
        if len(person.get('box',[]))!=4 or len(person.get('keypoints',[]))!=17 or not 0<=person.get('score',-1)<=1:raise ValueError('Invalid person')
        for i,v in enumerate(person['box']):
            if not isinstance(v,int) or not 0<=v<(width if i%2==0 else height):raise ValueError('Invalid box')
        for p in person['keypoints']:
            if p is not None and (not isinstance(p,list) or len(p)!=2 or not all(isinstance(v,int) for v in p) or not (0<=p[0]<width and 0<=p[1]<height)):
                raise ValueError('Invalid keypoint')
    return result

def receive(s,stop,emit,diagnostic=None):
    frame=None;header=None;data=bytearray();result=None;ended=False;sent_stop=False
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        if stop.is_set() and not sent_stop:s.write(b'cam_test stop\n');sent_stop=True
        line=s.readline().decode('ascii','replace').strip()
        if not line:continue
        if diagnostic is not None and not line.startswith('CAM_DATA '):diagnostic(line)
        if line.startswith('LIVE_START '):
            if frame:raise ValueError('Duplicate frame header')
            frame=json.loads(line[len('LIVE_START '):]);frame['received_at']=time.monotonic()
        elif line.startswith('CAM_BEGIN '):
            m=re.fullmatch(r'CAM_BEGIN (\d+) (\d+) (\d+) UYVY ([0-9a-fA-F]{8})',line)
            if not m or header or not frame:raise ValueError('Invalid frame header')
            n,w,h=map(int,m.groups()[:3])
            if (n,w,h)!=(38400,120,160):raise ValueError('Unexpected frame size')
            header=(n,w,h,int(m[4],16))
        elif line.startswith('CAM_DATA '):
            if not header:raise ValueError('Frame data before header')
            _,off,payload=line.split();block=bytes.fromhex(payload)
            if int(off)!=len(data) or not 0<len(block)<=96 or len(data)+len(block)>header[0]:raise ValueError('Frame offset/length error')
            data.extend(block)
        elif line.startswith('CAM_END '):
            _,n,check=line.split()
            if not header or int(n)!=header[0] or len(data)!=header[0] or int(check,16)!=header[3] or wire.fnv(data)!=header[3]:raise ValueError('Frame checksum failed')
            frame['raw']=bytes(data)
            frame['fnv32']=f'{header[3]:08x}'
            frame['sha256']=hashlib.sha256(data).hexdigest()
            frame['rgb'],frame['w'],frame['h']=orient(wire.decode_uyvy(data,120,160),120,160,frame['rotation'])
            ended=True
            if not stop.is_set():emit('frame',frame)
        elif line.startswith('POSE_RESULT '):
            if not ended or result:raise ValueError('Result without complete matching frame')
            result=validate_result(json.loads(line[len('POSE_RESULT '):]),frame)
            result['cycle_ms']=(time.monotonic()-frame['received_at'])*1000
        elif 'CAM_DONE ' in line:
            if stop.is_set():return None
            if 'result=OK streaming=OFF' not in line or not ended or result is None:raise RuntimeError('Incomplete capture/inference: '+line)
            frame['result']=result
            emit('result',frame)
            return frame
        elif ('CAM_ERROR' in line or 'CAM_ABORT' in line) and not stop.is_set():raise RuntimeError(line)
    try:s.write(b'cam_test stop\n')
    finally:raise TimeoutError('45 秒内未完成采集/推理；已请求停止')

def session(stop,emit,rotation=90,count=0,save=False):
    received=[]
    (ROOT/'evidence').mkdir(exist_ok=True)
    log_path=ROOT/'evidence'/('serial-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    with wire.connect() as s, log_path.open('w',encoding='utf-8') as log:
        s.baudrate=921600;s.reset_input_buffer()
        s.write(b'cam_test status\n')
        deadline=time.monotonic()+3;status=''
        while time.monotonic()<deadline:
            line=s.readline().decode('ascii','replace')
            if 'CAM_STATUS' in line:status=line;break
        if not status or 'busy=0' not in status:raise RuntimeError('未收到空闲状态。请确认实时姿态固件并关闭其他串口工具。')
        s.write(f'cam_test rotate{rotation}\n'.encode())
        deadline=time.monotonic()+3;ack=False
        while time.monotonic()<deadline:
            line=s.readline().decode('ascii','replace')
            if f'LIVE_ROTATION {rotation}' in line:ack=True;break
            if 'CAM_ERROR' in line:raise RuntimeError(line)
        if not ack:raise RuntimeError('方向设置未确认')
        emit('status','已连接。正在采集新画面…')
        try:
            while not stop.is_set() and (not count or len(received)<count):
                s.write(b'cam_test capture\n')
                frame=receive(s,stop,emit,lambda line:log.write(line+'\n'))
                if frame is None:break
                if save:save_frame(frame)
                if count:received.append(frame['result'])
        finally:
            # Camera streams are stopped before transfer/inference; no automatic requests after stop.
            s.write(b'cam_test stop\n')
    return received

def overlay(frame):
    rgb=bytearray(frame['rgb']);w,h=frame['w'],frame['h']
    result=frame.get('result')
    if not result:return bytes(rgb)
    def pixel(x,y,color):
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                xx,yy=x+dx,y+dy
                if 0<=xx<w and 0<=yy<h:rgb[(yy*w+xx)*3:(yy*w+xx)*3+3]=bytes(color)
    def line(a,b,color):
        x0,y0=a;x1,y1=b;n=max(abs(x1-x0),abs(y1-y0),1)
        for i in range(n+1):pixel(round(x0+(x1-x0)*i/n),round(y0+(y1-y0)*i/n),color)
    for person in result['people']:
        points=[None if p is None else (min(w-1,int(p[0]*w/result['width'])),min(h-1,int(p[1]*h/result['height']))) for p in person['keypoints']]
        for a,b in EDGES:
            if points[a] is not None and points[b] is not None:line(points[a],points[b],(0,255,120))
        x0,y0,x1,y1=person['box'];box=[(int(x0*w/result['width']),int(y0*h/result['height'])),(int(x1*w/result['width']),int(y1*h/result['height']))]
        for a,b in ((box[0],(box[1][0],box[0][1])),((box[1][0],box[0][1]),box[1]),(box[1],(box[0][0],box[1][1])),((box[0][0],box[1][1]),box[0])):line(a,b,(255,190,0))
        for p in points:
            if p is not None:pixel(*p,(255,60,120))
    return bytes(rgb)

def save_frame(frame):
    folder=ROOT/'captures'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
    (folder/'frame.uyvy').write_bytes(frame['raw'])
    (folder/'photo.png').write_bytes(wire.png(frame['rgb'],frame['w'],frame['h']))
    (folder/'pose.png').write_bytes(wire.png(overlay(frame),frame['w'],frame['h']))
    meta={k:v for k,v in frame.items() if k not in ('raw','rgb','received_at')}
    (folder/'result.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return folder

def gui(smoke=False,start_now=False):
    import tkinter as tk
    from tkinter import ttk
    app=tk.Tk();app.title('ESP32-S3 · YOLO11n-Pose 连续识别');app.geometry('900x760')
    msg=tk.StringVar(value='板端模型推理；点击开始。每次使用新画面，骨架只对应该次采集。')
    info=tk.StringVar(value='模型：COCO Pose S3 V1 / ESP-DL 3.3.14；未启动')
    age=tk.StringVar(value='尚未收到新画面')
    posture_text=tk.StringVar(value='坐姿实验功能：先开始识别，再校准坐姿。仅供姿态变化提醒。')
    monitor=posture.PostureMonitor()
    ttk.Label(app,textvariable=msg,wraplength=860).pack(pady=10)
    bar=ttk.Frame(app);bar.pack();events=queue.Queue();stop=threading.Event();active=False;closing=False;current=None;last_result=None
    angle=tk.StringVar(value='90')
    ttk.Label(bar,text='镜头顺时针旋转').pack(side='left')
    selector=ttk.Combobox(bar,textvariable=angle,values=('0','90','180','270'),width=5,state='readonly');selector.pack(side='left',padx=5)
    canvas=tk.Canvas(app,width=820,height=540,bg='#171a20',highlightthickness=0);canvas.pack(pady=10)
    ttk.Label(app,textvariable=info,wraplength=860).pack()
    ttk.Label(app,textvariable=age).pack()
    ttk.Label(app,textvariable=posture_text,wraplength=860,foreground='#244a72').pack(pady=4)
    ttk.Label(app,text='绿线：骨架　粉点：有效关键点　黄框：检测框。缺失关键点不补画。\n当前是低频连续推理；不提供医学坐姿判定。照片仅在“保存结果”时落盘。',foreground='#555').pack(pady=6)
    def emit(kind,value):events.put((kind,value))
    def draw(frame):
        nonlocal current
        current=frame;canvas.delete('all')
        zoom=min(4,820//frame['w'],540//frame['h'])
        im=tk.PhotoImage(data=wire.png(overlay(frame),frame['w'],frame['h'])).zoom(zoom,zoom)
        canvas.create_image(410,270,image=im);canvas.image=im
        if frame.get('result'):
            result=frame['result']
            for person in result['people']:
                x,y=person['box'][:2]
                ox=(820-frame['w']*zoom)/2;oy=(540-frame['h']*zoom)/2
                canvas.create_text(ox+x*frame['w']/result['width']*zoom,oy+y*frame['h']/result['height']*zoom-8,text=f"person {person['score']:.2f}",fill='#ffe29a',anchor='sw')
    def start():
        nonlocal active
        if active:return
        monitor.reset();posture_text.set('请坐稳并点击“校准坐姿”；重新开始后需要重新校准。')
        active=True;stop.clear();begin.configure(state='disabled');selector.configure(state='disabled');msg.set('正在连接开发板…')
        rotation=int(angle.get())
        def work():
            try:session(stop,emit,rotation)
            except Exception as e:emit('error',str(e))
            finally:emit('stopped',None)
        threading.Thread(target=work,daemon=True).start()
    def calibrate():
        if not active:
            posture_text.set('请先开始连续识别，再点击校准。');return
        monitor.start_calibration()
        posture_text.set('校准中：请保持舒适坐姿，等待 3 次有效结果。')
    def halt():
        if active:stop.set();msg.set('正在停止；若模型正在推理，等待本次推理返回，不再采集下一帧…')
    def save():
        if current and current.get('result'):msg.set('已保存到 '+str(save_frame(current)))
        else:msg.set('先等待一帧完整识别结果，再保存。')
    begin=ttk.Button(bar,text='开始连续识别',command=start);begin.pack(side='left',padx=8)
    ttk.Button(bar,text='停止',command=halt).pack(side='left',padx=5)
    ttk.Button(bar,text='校准坐姿',command=calibrate).pack(side='left',padx=5)
    ttk.Button(bar,text='保存结果',command=save).pack(side='left',padx=5)
    def close():
        nonlocal closing
        closing=True
        if active:halt()
        else:app.destroy()
    def poll():
        nonlocal active,last_result
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='frame':
                    draw(value);msg.set(f"新画面 #{value['id']} 已收到，正在板端推理；这一帧暂不显示旧骨架。")
                elif kind=='result':
                    draw(value);last_result=time.monotonic();r=value['result']
                    summary,_=monitor.update(r,last_result);posture_text.set(summary)
                    msg.set(f"帧 #{value['id']}：{len(r['people'])} 人；板端推理 {r['inference_ms']/1000:.2f} 秒")
                    points=', '.join(str(sum(p is not None for p in person['keypoints']))+'/17' for person in r['people']) or '无人'
                    info.set(f"图像 {r['width']}×{r['height']}；有效关键点 {points}；采集后传输+推理 {r['cycle_ms']/1000:.2f} 秒")
                elif kind in ('status','error'):msg.set(value)
                elif kind=='stopped':
                    monitor.reset();posture_text.set('已停止：坐姿校准已清除，重新开始后需重新校准。')
                    active=False;begin.configure(state='normal');selector.configure(state='readonly')
                    if closing:app.destroy();return
                    if stop.is_set():msg.set('已停止，串口已关闭。画面为上次采集。')
        except queue.Empty:pass
        if active and last_result is not None and time.monotonic()-last_result>30:
            posture_text.set('超过 30 秒没有新结果：坐姿状态已过期，请检查连接。')
        if current:age.set(f"当前画面采集后经过 {time.monotonic()-current['received_at']:.1f} 秒" if 'received_at' in current else '已保存的验收样例')
        app.after(100,poll)
    app.protocol('WM_DELETE_WINDOW',close);app.after(100,poll)
    if smoke:
        files=sorted((ROOT/'captures').glob('*/result.json'))
        if files:
            meta=json.loads(files[-1].read_text(encoding='utf-8'));raw=(files[-1].parent/'frame.uyvy').read_bytes()
            meta['raw']=raw;meta['rgb'],meta['w'],meta['h']=orient(wire.decode_uyvy(raw,120,160),120,160,meta['rotation']);draw(meta)
        def check():
            assert app.winfo_ismapped() and begin.winfo_ismapped() and not active
            assert current and canvas.find_all()
            print('Actual saved frame and model skeleton rendered; idle on launch');app.destroy()
        app.after(500,check)
    elif start_now:app.after(400,start)
    app.mainloop()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--frames',type=int,default=0);parser.add_argument('--rotation',type=int,choices=(0,90,180,270),default=90);parser.add_argument('--smoke-ui',action='store_true');parser.add_argument('--start',action='store_true');args=parser.parse_args()
    if args.frames:
        output=session(threading.Event(),lambda k,v:print(k,json.dumps(v['result'] if k=='result' else {'id':v['id']} if k=='frame' else v,ensure_ascii=False),flush=True),args.rotation,args.frames,True)
        (ROOT/'evidence/hardware-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    else:gui(args.smoke_ui,args.start)

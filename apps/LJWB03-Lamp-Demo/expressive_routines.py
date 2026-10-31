"""Small, model-aware lamp gestures. Geometry is an estimate, never feedback."""
import math

def lerp(a,b,t):return [round(x+(y-x)*t) for x,y in zip(a,b)]
def interp(points,pulse):
    for (a,b),(c,d) in zip(points,points[1:]):
        if pulse<=c:return b+(d-b)*(pulse-a)/(c-a)
    return points[-1][1]
def inverse(points,angle):
    pts=sorted((a,p) for p,a in points);angle=max(pts[0][0],min(pts[-1][0],angle))
    for (a,b),(c,d) in zip(pts,pts[1:]):
        if angle<=c:return round(b+(d-b)*(angle-a)/(c-a))
    return round(pts[-1][1])
def geometry(p,pulse):
    angles=[interp(c,v) for c,v in zip(p['calibration'],pulse)]
    xy=[(0.,0.)];a=-90
    for angle,length in zip(angles,p['lengths']):
        a+=angle;x,y=xy[-1];xy.append((x+length*math.cos(math.radians(a)),y+length*math.sin(math.radians(a))))
    return xy,a+(180 if p.get('head_face_sign',1)<0 else 0)
def face(p,pose,angle,home,limit=210):
    _,current=geometry(p,pose)
    delta=(angle-current+180)%360-180
    a=interp(p['calibration'][2],pose[2])+delta
    result=pose.copy();result[2]=max(500,home[2]-limit,min(2500,home[2]+limit,inverse(p['calibration'][2],a)))
    return result
def tilt(p,pose,delta,home):
    return face(p,pose,geometry(p,pose)[1]+delta,home)
def body(p,home,dx,dy,face_angle):
    """Search a small local neighbourhood, avoiding a large inverse-IK branch jump."""
    origin,_=geometry(p,home);goal=(origin[2][0]+dx,origin[2][1]+dy);best=None
    for da in range(-150,151,15):
        for db in range(-150,151,15):
            candidate=[max(500,min(2500,home[0]+da)),max(500,min(2500,home[1]+db)),home[2]]
            xy,_=geometry(p,candidate)
            cost=(xy[2][0]-goal[0])**2+(xy[2][1]-goal[1])**2+.005*(da*da+db*db)
            if best is None or cost<best[0]:best=(cost,candidate)
    return face(p,best[1],face_angle,home)
def trajectory_duration(start,row,cap):
    delays=row.get('delays',[0,0,0])
    # Quintic easing has a maximum slope of1.875. Include joint lag in the cap.
    return max(row['seconds'],max(1.875*abs(b-a)/(cap*(1-d)) for a,b,d in zip(start,row['pulse'],delays)))
def sample_motion(start,row,elapsed,cap):
    duration=trajectory_duration(start,row,cap);values=[]
    for a,b,delay in zip(start,row['pulse'],row.get('delays',[0,0,0])):
        u=max(0,min(1,(elapsed/duration-delay)/(1-delay)))
        ease=u*u*u*(10+u*(-15+6*u));values.append(round(a+(b-a)*ease))
    return values,duration

def build_gesture(p,roles,kind,music=False):
    home=p['poses'][roles['Rest']].copy();xy,heading=geometry(p,home)
    forward=1 if math.cos(math.radians(heading))>=0 else -1
    down=forward*1;up=-forward*1;length=sum(p['lengths'][:2])
    # Saved real checkpoints take priority. Starter guesses are replaced locally
    # by generated poses whose head height and facing are evaluated in the model.
    name=roles[kind];custom=not name.startswith('Starter ')
    target=p['poses'][name].copy() if custom else None
    rows=[]
    def add(label,pulse,seconds,pause=0,sound=-1,delays=(0,0,0)):
        rows.append(dict(name=label,pulse=pulse.copy(),seconds=seconds,pause=pause,sound=sound,easing='quintic',delays=list(delays)))
    happy=3 if music else 1
    add('Find a comfortable rest',home,1.1,.15)
    if kind=='Slump':
        target=target or body(p,home,forward*length*.025,length*.045,heading+down*18)
        glance=tilt(p,home,down*9,home)
        add('Eyelids heavy · head sinks first',glance,.75,delays=(0,0,0))
        add('Body gives in · head follows',target,1.8,1.0,2 if music else 0,delays=(.12,0,.2))
        effort=lerp(target,home,.18)
        add('A small effort to straighten',effort,.85,.2)
        add('Soft sigh · settle back',target,1.05,.55)
        notice=target.copy();notice[2]=lerp(target,home,.7)[2]
        add('Notice you · lift the face',notice,.85,.2)
        add('Recover · body follows the face',home,1.9,.15,delays=(.12,0,0))
        add('Thank-you nod',tilt(p,home,down*4,home),.55)
        add('Back with you',home,.8,.3,happy)
    elif kind=='Water':
        target=target or body(p,home,forward*length*.055,length*.015,heading+down*12)
        glance=home.copy();glance[2]=target[2]
        add('Notice the bottle · glance first',glance,.65,.2)
        add('Lean toward its fixed spot',target,1.35,.2,delays=(.12,0,0))
        point=tilt(p,target,down*5,home)
        add('There · a gentle invitation',point,.55,.2,5 if music else 4)
        add('Offer, do not insist',target,.8,1.4)
        back=target.copy();back[2]=home[2]
        add('Look back at you',back,.8,.15)
        add('Relax to rest',home,1.65,.3,delays=(.1,0,0))
    elif kind=='Stretch':
        target=target or body(p,home,-forward*length*.015,-length*.065,heading+up*13)
        dip=body(p,home,0,length*.012,heading+down*3)
        add('Gather a little breath',dip,.8,.2)
        first=dip.copy();first[2]=target[2]
        add('Breathe in · face rises first',first,.85,delays=(0,0,0))
        add('Unfold slowly · reach upward',target,2.4,1.6,7 if music else 6,delays=(.08,0,.18))
        settle=lerp(target,home,.08)
        add('Enjoy the stretch · soften the head',settle,1.0,.5)
        halfway=lerp(target,home,.55)
        add('Breathe out · let the links relax',halfway,1.6,delays=(0,.1,.2))
        add('Settle without snapping back',home,1.6,.15,delays=(0,.05,.12))
        add('Contented little nod',tilt(p,home,down*3,home),.55)
        add('Comfortable again',home,.85,.25,happy)
    else:raise ValueError('Unknown action')
    return rows

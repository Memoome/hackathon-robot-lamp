from pathlib import Path
import sys,copy,tempfile,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
import wireless_link
wireless_link.settings=lambda: {}
root=v.tk.Tk();root.withdraw();app=v.App(root);app.auto_connect.set(False)
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
 v.FILE=Path(temp)/'settings.json'
 original=copy.deepcopy(app.p);rows=[dict(name='arm',pulse=[1100,1500,1200],seconds=2,pause=0,sound=-1,base_pulse=2000),dict(type='base_position',name='turn',pulse=2200,seconds=2)]
 original_rows=copy.deepcopy(rows)
 app.disable_action_base.set(True)
 filtered=app.filter_action_base(rows)
 assert len(filtered)==1 and 'base_pulse' not in filtered[0]
 assert filtered[0]['pulse']==rows[0]['pulse'] and rows==original_rows
 for kind in ('Slump','Water','Stretch','Sad','Happy'):
  generated=app.action_rows(kind)
  assert generated and all('base_pulse' not in row and row.get('type') not in ('base','base_position') for row in generated),kind
 app.disable_action_base.set(False);assert app.filter_action_base(rows)==original_rows
 app.disable_action_base.set(True);app.preview_plan={'old':True};app.change_action_base()
 assert app.preview_plan is None and json.loads(v.FILE.read_text())['studio_ui']['disable_action_base'] is True
 assert app.p['calibration']==original['calibration'] and app.p['poses']==original['poses']
 assert app.link.jobs.empty() and not app.link.s
root.destroy();print('PASS: all five actions omit base motion when ticked; unchanged arm/light/sound rows, restored base when unticked, no stale plan or hardware commands.')

import copy,json,pathlib,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'))
import visual_control as v
snapshot=json.loads((v.PROFILES/'final draft.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as temp:
    v.FILE=pathlib.Path(temp)/'active.json';v.PROFILES=pathlib.Path(temp)/'profiles';v.PROFILES.mkdir()
    path=v.PROFILES/'final draft.json';path.write_text(json.dumps(snapshot),encoding='utf-8');original=path.read_bytes()
    v.FILE.write_text(json.dumps(snapshot),encoding='utf-8')
    root=v.tk.Tk();root.withdraw();app=v.App(root);app.auto_connect.set(False)
    app.profile_name.set('final draft');app.load_profile()
    assert app.p['calibration']==snapshot['calibration'] and app.p['config']==snapshot['config']
    assert app.profile_name.get()=='final draft (working copy)' and not app.p.get('profile_locked')
    app.p['calibration'][2]=v.reverse_mapping(app.p['calibration'][2],1101);app.save()
    app.profile_name.set('final draft')
    try:app.save_profile();raise AssertionError('Locked profile overwritten')
    except ValueError as exc:assert 'locked' in str(exc)
    app.profile_name.set('FINAL DRAFT')
    try:app.save_profile();raise AssertionError('Case bypass')
    except ValueError:pass
    app.profile_name.set('My adjustable lamp');app.save_profile()
    assert not json.loads((v.PROFILES/'My adjustable lamp.json').read_text()).get('profile_locked')
    assert path.read_bytes()==original and app.link.jobs.empty() and app.link.s is None
    app.link.closing=True;root.destroy()
print('PASS: exact locked load, overwrite/case protection, independent editable copy, immutable original and no board commands.')

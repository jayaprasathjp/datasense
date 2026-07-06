import modal
app = modal.App.lookup('datasense-sandbox', create_if_missing=True)
try:
    print('creating sandbox')
    sb = modal.Sandbox.create(app=app, timeout=1800)
    print('sandbox created:', sb.object_id)
    print('executing python...')
    p = sb.exec('python', '-c', 'print(\"hello from python\")')
    p.wait()
    print('stdout:', p.stdout.read())
except Exception as e:
    print('ERROR:', e)

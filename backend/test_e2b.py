import os
from e2b_code_interpreter import Sandbox
import inspect

print("Available methods in Sandbox:")
for name, member in inspect.getmembers(Sandbox):
    if not name.startswith("_"):
        print(name)

try:
    print("Trying Sandbox.create()...")
    s = Sandbox.create()
    print(s)
    s.close()
except Exception as e:
    print(e)

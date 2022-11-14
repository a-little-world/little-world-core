## Shell injects for running contains

Define any python script acessing backend instances.

Then run that script in the container by:

```shell
./run.py ma_shell_inject -i _shell_injects/script.py
```

This can be extremy helfull for debugging or bulk user creation see `./create_20_testusers.py`.

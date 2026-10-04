.RECIPEPREFIX = >
PY ?= C:\Python314\python.exe

.PHONY: test run scan scan-machine

test:
> $(PY) -m unittest discover -s tests -v

run:
> $(PY) -m rightmenu

scan:
> $(PY) -m rightmenu --scan --scope user

scan-machine:
> $(PY) -m rightmenu --scan --scope machine
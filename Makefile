.PHONY: install serve test clean

install:
	python3 -m pip install -e . --no-build-isolation --no-deps

serve:
	sonatarack serve --host 127.0.0.1 --port 11450

test:
	node --test tests/frontend.test.mjs
	python3 -m pytest -v

clean:
	rm -rf .pytest_cache src/*.egg-info

# Development

PittBOT is a discord bot written in Python, currently using the [Pycord](https://docs.pycord.dev/en/master/) discord API wrapper. 

## Using Python
The bot is programmed using Python 3.10. If you do not have Python 3.10 installed, you can get it from [here](https://www.python.org/downloads/release/python-3100/).

## Getting the code
To obtain a copy of the code, you can do one of the following:

1. [Fork the repository](https://docs.github.com/en/get-started/quickstart/fork-a-repo), then clone your fork. (This is the best option if you plan on making a pull request, which most contributors will do.)
2. Clone this repository directly.

To clone this repository, [ensure that Git is installed](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and, inside of a local folder which you would like to use for development, run the following:
```
git clone https://github.com/tjhubz/PittBOT .
```
or, if it is your fork,
```
git clone https://github.com/<YOUR GITHUB USERNAME>/PittBOT .
```

## Development Environment
During debugging stages, some core functionality relies on environment variables (like login token). It is recommended to use a virtual environment when developing because several external packages are required to use the bot.

### Using `venv`
Python's default virtual environment module is `venv`. To set up a virtual environment with venv, ensure you are in your local development directory (where the repository is) and run:

```
python -m venv env
```

Then, to activate the virtual environment in your terminal (which allows you to run commands in the environment), do the following:

**On Windows (CMD)**:\
Insert into `env/Scripts/activate.bat` the following line: `
```bat
set PITTBOT_TOKEN="token"
```
with the bot's login token at about line 12 (after the line that starts with `set VIRTUAL_ENV=`). Then run
```bat
"./env/Scripts/activate.bat"
```
in your command prompt. To deactivate, run
```bat
"./env/Scripts/deactivate.bat"
```

**On Windows (PowerShell)**:\
Insert into `env/Scripts/Activate.ps1` the following line:
```powershell
$env:PITTBOT_TOKEN = "token"
```
with the bot's login token at about line 168 (after "Begin Activate script" comment). Then run
```powershell
./env/Scripts/Activate.ps1
```
in your shell. To deactivate, run 
```powershell
deactivate
```

**On Unix (macOS/Linux)**:\
Insert into `env/Scripts/activate` the following lines:
```bash
PITTBOT_TOKEN="token"
export PITTBOT_TOKEN
```
with the bot's token at about line 43 (after `export VIRTUAL_ENV`). You may need to give this script permission to run. You can do so with
```bash
chmod +x ./env/Scripts/activate
```
Then run
```
./env/Scripts/activate
```
in your shell. To deactivate, run
```
deactivate
```

*All commands after this section assume you have set up a virtual environment or are okay with running these commands at a global or user level.*

## Installing Requisites

To install the requirements for development, run the following commands from the repository root directory:
```
pip install -r requirements.txt
```
or, on some Unix distributions
```
python3.10 -m pip install -r requirements.txt
```

**If your development would change the requirements for the bot**, please be sure to run
```
pip freeze > requirements.txt
```
or 
```
python3.10 -m pip freeze > requirements.txt
``` 
before committing your changes, so that others can easily install the added dependencies. 
Note: before running the above command, please **ensure you are in a virtual environment,** as it will otherwise add **all of the python packages installed on your system** to the requirements.

## Run the Bot
To run the bot, run:
```
python bot.py
```
or, on some Unix distributions
```
python3.10 bot.py
```

# Contributing your Changes

Starting in the fall semester of 2022, PittBOT will be running **live** on several ResLife servers, and so direct commits to the main, operating branch of the bot will be **disallowed**. Instead, we have set up a development branch `dev` where direct contributors can commit their changes. For others interested in making a pull request, **PRs will be made into the `dev` branch and not main**. 

When you plan on making a pull request, [fork the repository](https://docs.github.com/en/get-started/quickstart/fork-a-repo), ensure the repository is [synchronized](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork), and then [create a new branch](https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-a-branch-for-an-issue) to work on the specific issue that you are aiming to solve inside your fork. Once you are done working, you will make a pull request back into this repository. You can learn how to make a pull request from your fork repository [here](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request), and learn to change the base branch to pull into `dev` [here](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/changing-the-base-branch-of-a-pull-request). 

Periodically, updates from the `dev` branch will be merged into `main` and become live in the bot, after ensuring they are stable enough to deploy.

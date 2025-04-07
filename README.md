# pollevbot

**pollevbot** is a bot that automatically responds to polls on [pollev.com](https://pollev.com/). 
It continually checks if a specified host has opened any polls. Once a poll has been opened, 
it uses Claude AI to generate appropriate responses.

Requires Python 3.7 or later.
## Dependencies

[Requests](https://pypi.org/project/requests/), 
[BeautifulSoup](https://pypi.org/project/beautifulsoup4/),
[Anthropic](https://pypi.org/project/anthropic/),
[Flask](https://pypi.org/project/Flask/) (for web GUI).

[APScheduler](https://pypi.org/project/APScheduler/) to deploy to Heroku.

## Usage

### Command Line Interface

Install `pollevbot`:
```
pip install -r requirements.txt
```

Set your username, password, and desired poll host:
```python
user = 'My Username'
password = 'My Password'
host = 'PollEverywhere URL Extension e.g. "uwpsych"'
```

And run the script.
```python
from pollevbot import PollBot

user = 'My Username'
password = 'My Password'
host = 'PollEverywhere URL Extension e.g. "uwpsych"'
claude_api_key = 'Your Claude API Key'

# If you're using a non-UW PollEv account,
# add the argument "login_type='pollev'"
with PollBot(
    user, 
    password, 
    host, 
    login_type='pollev',
    claude_api_key=claude_api_key
) as bot:
    bot.run()
```
Alternatively, you can clone this repo, set your login credentials in 
[main.py](main.py) and run it from there.

### Web Interface

PollEvBot now includes a web interface for easier configuration and monitoring. To start the web interface:

```bash
python webgui.py
```

By default, the web interface will be available at http://localhost:5000. You can customize the host and port:

```bash
python webgui.py --host 127.0.0.1 --port 8080
```

The web interface allows you to:
- Configure PollEverywhere credentials and other settings
- Start and stop the bot
- Monitor recent poll responses
- Adjust wait times and other operational parameters

## Heroku

**pollevbot** can be scheduled to run at specific dates/times (UTC timezone) using [Heroku](http://heroku.com/):

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/danielqiang/pollevbot)

Required configuration variables:

* `DAY_OF_WEEK`: [cron](https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html) string
specifying weekdays to run pollevbot (e.g. `mon,wed` is Monday and Wednesday).
* `HOUR`: [cron](https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html) string
(UTC time) specifying which hours to run pollevbot.
* `LIFETIME`: Time to run pollevbot before terminating (in seconds). Set to `inf` to run forever.
* `LOGIN_TYPE`: Login protocol to use (either `uw` or `pollev`).
* `MINUTE`: [cron](https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html) string
specifying what minutes to run pollevbot.
* `PASSWORD`: PollEv account password.
* `POLLHOST`: PollEv host name.
* `USERNAME`: PollEv account username.
* `CLAUDE_API_KEY`: API key for Claude AI.
* `TELEGRAM_BOT_TOKEN`: (Optional) Token for Telegram bot integration.
* `TELEGRAM_ADMIN_CHAT_ID`: (Optional) Chat ID for admin notifications.

**Example**

Suppose you want to answer polls made by poll host `teacher123` every Monday and Wednesday 
from 11:30 AM to 12:30 PM PST (6:30 PM to 7:30 PM UTC) in your timezone on your UW account. To do this, set the config 
variables as follows:

* `DAY_OF_WEEK`: `mon,wed`
* `HOUR`: `18`
* `LIFETIME`: `3600`
* `LOGIN_TYPE`: `uw`
* `MINUTE`: `30`
* `PASSWORD`: `yourpassword`
* `POLLHOST`: `teacher123`
* `USERNAME`: `yourusername`
* `CLAUDE_API_KEY`: `your-claude-api-key`

Then click `Deploy App` and wait for the app to finish building. 
**pollevbot** is now deployed to Heroku! 

## Configuration Options

The bot can be configured with the following options:

* `min_option`: Minimum index (0-indexed) of option to select (inclusive)
* `max_option`: Maximum index (0-indexed) of option to select (exclusive)
* `closed_wait`: Time to wait in seconds if no polls are open before checking again (default: 5)
* `open_wait`: Time to wait in seconds if a poll is open before answering (default: 60)
* `lifetime`: Lifetime of this PollBot in seconds (default: infinite)
* `log_file`: File path for logging responses (default: "poll_responses.jsonl")

## Disclaimer

I do not promote or condone the usage of this script for any kind of academic misconduct 
or dishonesty. I wrote this script for the sole purpose of educating myself on cybersecurity 
and web protocol automation, and cannot be held liable for any indirect, incidental, consequential, 
special, or exemplary damages arising out of or in connection with the usage of this script.

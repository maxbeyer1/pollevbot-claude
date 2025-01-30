import os
from dotenv import load_dotenv

from pollevbot import PollBot


def get_env_var(var_name: str) -> str:
    """
    Get an environment variable from .env file or system environment

    Args:
        var_name: The name of the environment variable

    Returns:
        The value of the environment variable
    """
    value = os.getenv(var_name)

    if value is None:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value


def main():
    # Load environment variables from .env file
    load_dotenv()

    # Required environment variables
    required_vars = {
        'POLLEV_USERNAME': 'username for PollEverywhere',
        'POLLEV_PASSWORD': 'password for PollEverywhere',
        'POLLEV_HOST': 'host for PollEverywhere (e.g. "uwpsych")',
        'CLAUDE_API_KEY': 'API key for Claude AI'
    }

    # Check if any required variables are missing
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print("Missing required environment variables:")
        for var in missing:
            print(f"  {var}: {required_vars[var]}")
        return

    # Get all required variables
    user = get_env_var('POLLEV_USERNAME')
    password = get_env_var('POLLEV_PASSWORD')
    host = get_env_var('POLLEV_HOST')
    claude_api_key = get_env_var('CLAUDE_API_KEY')

    # If you're using a non-uw PollEv account,
    # add the argument "login_type='pollev'"
    with PollBot(user, password, host, login_type='pollev', claude_api_key=claude_api_key) as bot:
        bot.run()


if __name__ == '__main__':
    main()

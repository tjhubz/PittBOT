"""Logging module for prettier console logs.
"""

import datetime
import termcolor

class Log:
    """Logging class used for more readable bot logs.

    Logs with both current time and logging level, colorized where supported.
    """

    def error(msg: str):
        """Log an error to console.

        Args:
            msg (str): Message to log as error
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = termcolor.colored("ERROR", "red")
        print(f"[ {now} ][ {level} ] {msg}")

    def warning(msg: str):
        """Log a warning to console.

        Args:
            msg (str): Message to log as warning
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = termcolor.colored("WARN", "yellow")
        print(f"[ {now} ][ {level} ] {msg}")

    # pylint: disable=invalid-name
    def ok(msg: str):
        """Log a success message to console.

        Args:
            msg (str): Message to log as OK
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = termcolor.colored("OK", "green")
        print(f"[ {now} ][ {level} ] {msg}")

    def info(msg: str):
        """Log an info line to console.

        Args:
            msg (str): Message to log as info
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[ {now} ][ INFO ] {msg}")

import termcolor

class Log:
    def error(msg: str):
        level = termcolor.colored(f"ERROR", "red")
        print(f"[ {level} ] {msg}")

    def warning(msg: str):
        level = termcolor.colored(f"WARN", "yellow")
        print(f"[ {level} ] {msg}")

    def ok(msg: str):
        level = termcolor.colored(f"OK", "green")
        print(f"[ {level} ] {msg}")

    def info(msg: str):
        print(f"[ INFO ] {msg}")
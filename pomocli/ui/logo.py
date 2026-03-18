from rich.console import Console

def print_logo():
    console = Console()
    logo = [
        "        [green]██[/green][green]██[/green][green]██[/green][green]██[/green]                ",
        "      [green]██[/green][green]██[/green][green]██[/green][green]██[/green][green]██[/green][green]██[/green]              ",
        "    [green]██[/green][green]██[/green]    [green]██[/green][green]██[/green]                ",
        "    [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red]        ",
        "  [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red]    ",
        "[red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "[red]██[/red][red]██[/red][red]██[/red][white]██[/white][white]██[/white][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "[red]██[/red][red]██[/red][red]██[/red][white]██[/white][white]██[/white][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "[red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "[red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "[red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]  ",
        "  [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]    ",
        "  [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]    ",
        "    [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][dark_red]██[/dark_red][dark_red]██[/dark_red]      ",
        "        [red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red][red]██[/red]          ",
        "                                ",
    ]
    for line in logo:
        console.print(line)

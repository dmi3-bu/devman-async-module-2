# type: ignore

import asyncio
import curses
import random
import time
from itertools import cycle
from os import listdir

from curses_tools import draw_frame, get_frame_size, read_controls
from explosion import explode
from obstacles import Obstacle
from physics import update_speed

TIC_TIMEOUT = 0.1
STARS_COUNT = 50
PADDING = 1
SYMBOLS = ['+', '*', '.', ':']
STAR_SIZE = 1
STARTING_YEAR = 1957
CANNON_UNLOCKED_YEAR = 2020
NEXT_YEAR_THRESHOLD = 1.5
PHRASES = {
    1957: "First Sputnik",
    1961: "Gagarin flew!",
    1969: "Armstrong got on the moon!",
    1971: "First orbital space station Salute-1",
    1981: "Flight of the Shuttle Columbia",
    1998: 'ISS start building',
    2011: 'Messenger launch to Mercury',
    2020: "Take the plasma gun! Shoot the garbage!",
}

global coroutines
coroutines = []
global obstacles
obstacles = []
global obstacles_in_last_collisions
obstacles_in_last_collisions = []
global year
year = STARTING_YEAR
max_text_length = len(max(PHRASES.values(), key=len)) + 20


def init_rocket_frames():
    rocket_frame_1 = open('frames/rocket/rocket_frame_1.txt').read()
    rocket_frame_2 = open('frames/rocket/rocket_frame_2.txt').read()
    return [rocket_frame_1, rocket_frame_2, rocket_frame_2, rocket_frame_2]


rocket_frames = init_rocket_frames()


def measure_jet_length():
    rocket_lines = rocket_frames[0].splitlines()
    jet_start = next((i for i, line in enumerate(rocket_lines) if '(' in line or ')' in line))
    jet_end = len(rocket_lines)
    return jet_end - jet_start


def garbage_frames():
    frames = []
    for filename in listdir('frames/trash'):
        frame = open('frames/trash/' + filename).read()
        frames.append(frame)
    return frames


def draw(canvas):
    curses.curs_set(False)
    canvas.nodelay(True)
    canvas.border()

    global max_row, max_column
    max_row, max_column = canvas.getmaxyx()
    text_window = canvas.subwin(max_row - 3, max_column-max_text_length)
    text_window.border()

    init_rocket_row = max_row/2
    init_rocket_col = max_column/2

    spawn_stars(canvas)

    spaceship = animate_spaceship(canvas, rocket_frames, init_rocket_row, init_rocket_col)
    garbage_filler = fill_orbit_with_garbage(canvas)
    year_counter = show_year(canvas)
    coroutines.extend([spaceship, garbage_filler, year_counter])

    seconds_since_new_year = 0

    while True:
        for coroutine in coroutines.copy():
            try:
                coroutine.send(None)
            except StopIteration:
                coroutines.remove(coroutine)

        canvas.refresh()
        time.sleep(TIC_TIMEOUT)
        seconds_since_new_year = keep_time(seconds_since_new_year)


def spawn_stars(canvas):
    for _ in range(STARS_COUNT):
        row = random.randint(0 + PADDING, max_row - PADDING - STAR_SIZE)
        column = random.randint(0 + PADDING, max_column - PADDING - STAR_SIZE)
        sign = random.choice(SYMBOLS)
        offset_ticks = random.randint(0, 5)
        star = blink(canvas, row, column, offset_ticks, sign)
        coroutines.append(star)


def keep_time(seconds_since_new_year):
    seconds_since_new_year += TIC_TIMEOUT
    if seconds_since_new_year >= NEXT_YEAR_THRESHOLD:
        seconds_since_new_year = 0
        global year
        year += 1
    return seconds_since_new_year


async def blink(canvas, row, column, offset_ticks, symbol='*'):
    while True:
        canvas.addstr(row, column, symbol, curses.A_DIM)
        await sleep(20)

        canvas.addstr(row, column, symbol, curses.A_DIM)
        await sleep(offset_ticks)

        canvas.addstr(row, column, symbol)
        await sleep(3)

        canvas.addstr(row, column, symbol, curses.A_BOLD)
        await sleep(5)

        canvas.addstr(row, column, symbol)
        await sleep(3)


async def fire(canvas,
               start_row,
               start_column,
               rows_speed=-0.3,
               columns_speed=0):
    """Display animation of gun shot, direction and speed can be specified."""

    row, column = start_row, start_column

    canvas.addstr(round(row), round(column), '*')
    await asyncio.sleep(0)

    canvas.addstr(round(row), round(column), 'O')
    await asyncio.sleep(0)
    canvas.addstr(round(row), round(column), ' ')

    row += rows_speed
    column += columns_speed

    symbol = '-' if columns_speed else '|'

    curses.beep()

    while 0 < row < max_row - PADDING and 0 < column < max_column - PADDING:
        for obstacle in obstacles:
            if obstacle.has_collision(row, column):
                obstacles_in_last_collisions.append(obstacle)
                return

        canvas.addstr(round(row), round(column), symbol)
        await asyncio.sleep(0)
        canvas.addstr(round(row), round(column), ' ')
        row += rows_speed
        column += columns_speed


async def animate_spaceship(canvas, frames, row, column):
    row_speed = column_speed = 0

    rocket_rows, rocket_cols = get_frame_size(frames[0])
    jet_length = measure_jet_length()

    for frame in cycle(frames):
        row_dir, column_dir, space_pr = read_controls(canvas)
        row_speed, column_speed = update_speed(row_speed, column_speed, row_dir, column_dir)
        row, column = row + row_speed, column + column_speed

        row = limit_boundary(row, 0 + PADDING, max_row - rocket_rows - PADDING)
        column = limit_boundary(column, 0 + PADDING, max_column - rocket_cols - PADDING)

        if space_pr and year >= CANNON_UNLOCKED_YEAR:
            shot = fire(canvas, row - 1, column + 2)
            coroutines.append(shot)

        draw_frame(canvas, row, column, frame)
        await asyncio.sleep(0)
        draw_frame(canvas, row, column, frame, True)

        for obstacle in obstacles:
            if obstacle.has_collision(row, column, rocket_rows, rocket_cols - jet_length):
                gameover_sign = show_gameover(canvas)
                coroutines.append(gameover_sign)
                return


def limit_boundary(dimension, min_dim, max_dim):
    dimension = max(dimension, min_dim)
    dimension = min(dimension, max_dim)
    return dimension


async def sleep(tics=1):
    for _ in range(tics):
        await asyncio.sleep(0)


async def fly_garbage(canvas, column, garbage_frame, speed=0.5):
    """Animate garbage, flying from top to bottom. Column position will stay same, as specified on start."""
    rows_number, columns_number = canvas.getmaxyx()

    column = max(column, 0)
    column = min(column, columns_number - 1)
    row = 0

    while row < rows_number:
        draw_frame(canvas, row, column, garbage_frame)

        obs_rows, obs_cols = get_frame_size(garbage_frame)
        obstacle = Obstacle(row, column, obs_rows, obs_cols)
        obstacles.append(obstacle)

        await asyncio.sleep(0)
        draw_frame(canvas, row, column, garbage_frame, negative=True)

        obstacles.remove(obstacle)
        if obstacle in obstacles_in_last_collisions:
            obstacles_in_last_collisions.remove(obstacle)
            explosion = explode(canvas, row + (obs_rows/2) + 1, column + (obs_cols/2) - 2)
            coroutines.append(explosion)
            return

        row += speed


async def fill_orbit_with_garbage(canvas):
    while True:
        delay_ticks = get_garbage_delay_tics(year)

        if not delay_ticks:
            await asyncio.sleep(0)
            continue

        garbage_frame = random.choice(garbage_frames())
        _, cols = get_frame_size(garbage_frame)
        garbage_position = random.randint(1, max_column - cols)
        garbage = fly_garbage(canvas, garbage_position, garbage_frame)
        coroutines.append(garbage)
        await sleep(delay_ticks)


def get_garbage_delay_tics(year):
    if year < 1961:
        return None
    elif year < 1969:
        return 20
    elif year < 1981:
        return 14
    elif year < 1995:
        return 10
    elif year < 2010:
        return 8
    elif year < 2020:
        return 6
    else:
        return 2


async def show_year(canvas):
    while True:
        text = f"      Year {str(year)}    "
        if news := PHRASES.get(year):
            text = news + text
        text = text.rjust(max_text_length, ' ')

        draw_frame(canvas, max_row-2, max_column-max_text_length, text)
        await asyncio.sleep(0)
        draw_frame(canvas, max_row-2, max_column-max_text_length, text, negative=True)


async def show_gameover(canvas):
    game_over_sign = open('frames/game_over.txt').read()
    while True:
        rows, cols = get_frame_size(game_over_sign)
        row, col = max_row/2 - rows/2, max_column/2 - cols/2

        draw_frame(canvas, row, col, game_over_sign)
        await asyncio.sleep(0)
        draw_frame(canvas, row, col, game_over_sign, negative=True)


if __name__ == '__main__':
    curses.update_lines_cols()
    try:
        curses.wrapper(draw)
    except KeyboardInterrupt:
        quit()

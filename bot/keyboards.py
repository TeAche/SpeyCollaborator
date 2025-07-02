from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_cancel_keyboard(text: str = 'Отмена') -> InlineKeyboardMarkup:
    print('DEBUG: build_cancel_keyboard')
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data='cancel')]])


def build_keyboard(tasks, include_add_button: bool = False, include_back_button: bool = False) -> InlineKeyboardMarkup | None:
    print('DEBUG: build_keyboard')
    keyboard = []
    print(f'DEBUG: build_keyboard received {len(tasks)} tasks')
    for task in tasks:
        if not task.get('done'):
            keyboard.append([
                InlineKeyboardButton(
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')})" +
                    (f" [{', '.join(task.get('tags', []))}]" if task.get('tags') else ''),
                    callback_data=f"task_{task['id']}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton('🏷️', callback_data=f"tag_{task['id']}"),
                InlineKeyboardButton('✏️', callback_data=f"edit_{task['id']}"),
                InlineKeyboardButton('🗑️', callback_data=f"delete_{task['id']}"),
            ])
    if include_add_button:
        keyboard.append([InlineKeyboardButton('Добавить задачу', callback_data='add_task')])
    if include_back_button:
        keyboard.append([InlineKeyboardButton('Назад', callback_data='cancel')])
    if keyboard:
        print(f'DEBUG: build_keyboard -> {len(keyboard)} rows')
        return InlineKeyboardMarkup(keyboard)
    print('WARNING: build_keyboard produced empty keyboard')
    return InlineKeyboardMarkup([[InlineKeyboardButton('Добавить задачу', callback_data='add_task')]]) if include_add_button else None


def build_completed_keyboard(tasks, include_back_button: bool = False) -> InlineKeyboardMarkup | None:
    print('DEBUG: build_completed_keyboard')
    keyboard = []
    print(f'DEBUG: build_completed_keyboard received {len(tasks)} tasks')
    for task in tasks:
        if task.get('done'):
            keyboard.append([
                InlineKeyboardButton(
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')})" +
                    (f" [{', '.join(task.get('tags', []))}]" if task.get('tags') else '') + ' ✓',
                    callback_data=f"restore_{task['id']}"
                )
            ])
    if include_back_button:
        keyboard.append([InlineKeyboardButton('Назад', callback_data='cancel')])
    if keyboard:
        print(f'DEBUG: build_completed_keyboard -> {len(keyboard)} rows')
        return InlineKeyboardMarkup(keyboard)
    return None


def build_category_keyboard(categories, include_new=True):
    print('DEBUG: build_category_keyboard')
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"choose_cat_{i}")]
                for i, cat in enumerate(categories)]
    if include_new:
        keyboard.append([InlineKeyboardButton('Новая категория', callback_data='new_category')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)


def build_priority_keyboard():
    print('DEBUG: build_priority_keyboard')
    keyboard = [
        [InlineKeyboardButton('низкий', callback_data='priority_низкий')],
        [InlineKeyboardButton('средний', callback_data='priority_средний')],
        [InlineKeyboardButton('высокий', callback_data='priority_высокий')],
        [InlineKeyboardButton('Отмена', callback_data='cancel')],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_filter_category_keyboard(categories):
    print('DEBUG: build_filter_category_keyboard')
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"fcat_{i}")]
                for i, cat in enumerate(categories)]
    keyboard.append([InlineKeyboardButton('Любая', callback_data='fcat_none')])
    keyboard.append([InlineKeyboardButton('Назад', callback_data='filter')])
    return InlineKeyboardMarkup(keyboard)


def build_filter_priority_keyboard():
    print('DEBUG: build_filter_priority_keyboard')
    keyboard = [
        [InlineKeyboardButton('низкий', callback_data='fprio_низкий')],
        [InlineKeyboardButton('средний', callback_data='fprio_средний')],
        [InlineKeyboardButton('высокий', callback_data='fprio_высокий')],
        [InlineKeyboardButton('Любой', callback_data='fprio_none')],
        [InlineKeyboardButton('Назад', callback_data='filter')],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_filter_tag_keyboard(tags):
    print('DEBUG: build_filter_tag_keyboard')
    keyboard = [[InlineKeyboardButton(tag, callback_data=f"ftag_{i}")]
                for i, tag in enumerate(tags)]
    keyboard.append([InlineKeyboardButton('Любой', callback_data='ftag_none')])
    keyboard.append([InlineKeyboardButton('Назад', callback_data='filter')])
    return InlineKeyboardMarkup(keyboard)


def build_tag_keyboard(tags, include_new=True):
    print('DEBUG: build_tag_keyboard')
    keyboard = [[InlineKeyboardButton(tag, callback_data=f"choose_tag_{i}")]
                for i, tag in enumerate(tags)]
    if include_new:
        keyboard.append([InlineKeyboardButton('Новый тег', callback_data='new_tag')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)

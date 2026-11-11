import os
import re
import html
import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ChatMember,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token Bot Telegram
TOKEN = os.getenv("BOT_TOKEN", "").strip() or "9042194702:AAEGuKY5Mq0oaBX_IoEOB9xMsQENktxnhjA"

try:
    TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    from datetime import timezone
    TIMEZONE = timezone(timedelta(hours=7))

# Quản lý tiến trình hẹn theo (chat_id, user_id)
active_reminders = {}


def get_user_mention(user):
    safe_name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{safe_name}</a>'


def make_styled_button(text: str, style_type: str = "secondary") -> KeyboardButton:
    """
    Tạo nút bấm kèm đầy đủ các trường thuộc tính màu (style, color, bg_color).
    - style_type='success' -> Xanh lá (#4CAF50)
    - style_type='danger'  -> Đỏ (#E53935)
    - style_type='primary' -> Xanh dương (#2196F3)
    """
    color_map = {
        "success": {"color": "green", "bg_color": "#4CAF50"},
        "danger":  {"color": "red",   "bg_color": "#E53935"},
        "primary": {"color": "blue",  "bg_color": "#2196F3"},
        "secondary": {"color": "gray", "bg_color": "#242F3D"}
    }
    extra_data = {
        "style": style_type,
        "color": color_map.get(style_type, {}).get("color", "gray"),
        "bg_color": color_map.get(style_type, {}).get("bg_color", "#242F3D")
    }
    return KeyboardButton(text=text, api_kwargs=extra_data)


def get_keyboard():
    """Tạo bàn phím 4 nút với thuộc tính màu tương ứng"""
    keyboard = [
        # Hàng 1: 3 nút Xanh lá
        [
            make_styled_button("10 Phút", style_type="success"),
            make_styled_button("20 Phút", style_type="success"),
            make_styled_button("30 Phút", style_type="success"),
        ],
        # Hàng 2: 1 nút Đỏ trải dài
        [
            make_styled_button("🛑 Dừng nhắc nhở", style_type="danger")
        ]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Bấm chọn mốc thời gian hoặc bấm Dừng..."
    )


async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bot Nhắc Đánh Thẻ / Chấm Công</b>\n\n"
        "Vui lòng bấm chọn mốc thời gian bên dưới khung chat, hoặc gõ nhanh: <b>10</b>, <b>20</b>, <b>30</b>, <b>dừng</b>:"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_keyboard(),
        parse_mode="HTML"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_menu(update.effective_chat.id, context)


async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result:
        new_member = result.new_chat_member
        if new_member.user.id == context.bot.id and new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
            await asyncio.sleep(1)
            await send_menu(update.effective_chat.id, context)


async def cancel_reminder(chat_id: int, user_id: int):
    """Hủy tiến trình hẹn giờ của một cá nhân"""
    key = (chat_id, user_id)
    if key in active_reminders:
        task = active_reminders[key].get("task")
        if task and not task.done():
            task.cancel()
        del active_reminders[key]
        return True
    return False


async def start_reminder_timer(chat_id: int, user, minutes: int, context: ContextTypes.DEFAULT_TYPE, message_obj):
    key = (chat_id, user.id)
    mention = get_user_mention(user)

    # 1. Chặn tạo lịch mới nếu đang có lịch chưa hoàn thành
    if key in active_reminders:
        existing = active_reminders[key]
        time_str = existing.get("time_str", "sắp tới")
        orig_min = existing.get("minutes", "")
        await message_obj.reply_text(
            f"⚠️ {mention}, bạn đang có một lịch hẹn <b>{orig_min} phút</b> chưa hoàn thành (dự kiến nhắc lúc <b>{time_str}</b>)!\n"
            f"👉 Bạn không thể đặt thêm lịch mới. Vui lòng bấm <b>🛑 Dừng nhắc nhở</b> nếu muốn hủy hoặc chờ đến giờ để bấm xác nhận <b>OK</b>.",
            parse_mode="HTML"
        )
        return

    # 2. Tạo lịch hẹn mới độc lập cho cá nhân này
    wait_minutes = max(1, minutes - 1)  # Trừ hao nhắc trước 1 phút
    now_vn = datetime.now(TIMEZONE)
    reminder_time = now_vn + timedelta(minutes=wait_minutes)
    time_str = reminder_time.strftime("%H:%M:%S")

    await message_obj.reply_text(
        f"✅ {mention} đã hẹn giờ <b>{minutes} phút</b>.\n"
        f"Bot sẽ nhắc nhở vào lúc: <b>{time_str}</b>",
        parse_mode="HTML"
    )

    task = asyncio.create_task(
        reminder_countdown(chat_id, wait_minutes, user.id, mention, context)
    )
    active_reminders[key] = {
        "task": task,
        "time_str": time_str,
        "minutes": minutes
    }


async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt và bóc tách dữ liệu tin nhắn hoặc nút bấm"""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    mention = get_user_mention(user)
    raw_text = update.message.text.strip()
    lower_text = raw_text.lower()

    # Xử lý lệnh Dừng
    if any(w in lower_text for w in ["dung", "dừng", "stop", "hủy", "huy", "🛑", "🔴"]):
        if not re.search(r'\b(10|20|30)\b', lower_text):
            canceled = await cancel_reminder(chat_id, user.id)
            if canceled:
                await update.message.reply_text(f"🛑 {mention} đã hủy lịch nhắc nhở thành công!", parse_mode="HTML")
            else:
                await update.message.reply_text(f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.", parse_mode="HTML")
            return

    # Xử lý mốc thời gian 10, 20, 30 phút
    match = re.search(r'\b(10|20|30)\b', lower_text)
    if match:
        minutes = int(match.group(1))
        await start_reminder_timer(chat_id, user, minutes, context, update.message)


async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    key = (chat_id, target_user_id)
    try:
        await asyncio.sleep(wait_minutes * 60)

        keyboard = [[InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Lặp lại nhắc nhở sau mỗi 15 giây (tối đa 15 lần)
        for _ in range(15):
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ {user_mention} <b>ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!</b>\n"
                    "Vui lòng bấm nút OK bên dưới để tắt thông báo."
                ),
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            await asyncio.sleep(15)

    except asyncio.CancelledError:
        logger.info(f"Đã hủy lịch nhắc cho user {target_user_id}")
    except Exception as e:
        logger.error(f"Lỗi gửi tin trong countdown: {e}")
    finally:
        if key in active_reminders and active_reminders[key].get("task") == asyncio.current_task():
            del active_reminders[key]


async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    target_user_id_str = data.split("_")[1]

    # Kiểm tra chỉ người đặt lịch mới được tắt
    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải người đặt lịch này nên không thể bấm tắt!", show_alert=True)
        return

    await query.answer()
    chat_id = query.message.chat_id

    # Giải phóng tiến trình để người dùng có thể đặt lịch tiếp theo
    await cancel_reminder(chat_id, user.id)

    mention = get_user_mention(user)
    await query.edit_message_text(
        text=f"👍 <b>{mention} đã đánh thẻ thành công!</b> Đã tắt nhắc nhở.",
        parse_mode="HTML"
    )


def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_incoming_message))

    logger.info("Bot đang kết nối Telegram...")
    application.run_polling()


if __name__ == "__main__":
    main()

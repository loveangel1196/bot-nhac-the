import os
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
    WebAppInfo,
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

# Cấu hình log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay thế bằng Token BotFather mới của bạn (hoặc thiết lập biến môi trường BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN", "9042194702:AAEGuKY5Mq0oaBX_IoEOB9xMsQENktxnhjA")

# Đường dẫn GitHub Pages chứa file index.html
WEB_APP_URL = "https://loveangel1196.github.io/bot-nhac-the/"

# Múi giờ Việt Nam
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Quản lý tiến trình nhắc nhở theo (chat_id, user_id)
active_reminders = {}


def get_user_mention(user):
    """Tạo tag tên an toàn chống lỗi cú pháp HTML"""
    safe_name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{safe_name}</a>'


def get_main_reply_keyboard():
    """Tạo bàn phím cố định dưới khung chat để kích hoạt Web App hợp lệ"""
    keyboard = [
        [KeyboardButton("🎨 Mở bảng chọn thời gian (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton("🛑 Dừng nhắc nhở")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bot Nhắc Đánh Thẻ / Chấm Công</b>\n\n"
        "• Bấm nút <b>🎨 Mở bảng chọn thời gian</b> ở bàn phím bên dưới để mở giao diện HTML.\n"
        "• Hoặc bạn có thể gõ nhanh trực tiếp: <b>10</b>, <b>20</b>, <b>30</b> hoặc <b>dừng</b>."
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_main_reply_keyboard(),
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
    """Hủy tiến trình đang chạy của người dùng trong nhóm/chat"""
    key = (chat_id, user_id)
    if key in active_reminders:
        active_reminders[key]["task"].cancel()
        del active_reminders[key]
        return True
    return False


async def start_reminder_timer(chat_id: int, user, minutes: int, context: ContextTypes.DEFAULT_TYPE, reply_to_message):
    wait_minutes = max(1, minutes - 1)  # Trừ hao nhắc trước 1 phút
    key = (chat_id, user.id)

    await cancel_reminder(chat_id, user.id)

    now_vn = datetime.now(TIMEZONE)
    reminder_time = now_vn + timedelta(minutes=wait_minutes)
    time_str = reminder_time.strftime("%H:%M:%S")
    mention = get_user_mention(user)

    await reply_to_message.reply_text(
        f"✅ {mention} đã hẹn giờ <b>{minutes} phút</b>.\n"
        f"Bot sẽ nhắc nhở vào lúc: <b>{time_str}</b>",
        parse_mode="HTML"
    )

    task = context.application.create_task(
        reminder_countdown(chat_id, wait_minutes, user.id, mention, context)
    )
    active_reminders[key] = {"task": task}


async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý dữ liệu trả về từ Web App (HTML) hoặc tin nhắn chữ thường"""
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    mention = get_user_mention(user)
    raw_text = None

    # 1. Nhận dữ liệu gửi từ file index.html qua tg.sendData()
    if update.message.web_app_data:
        raw_text = update.message.web_app_data.data.strip().lower()

    # 2. Hoặc nhận dữ liệu khi người dùng gõ phím trực tiếp
    elif update.message.text:
        raw_text = update.message.text.strip().lower()

    if not raw_text:
        return

    # Xử lý lệnh dừng
    if raw_text in ["dung", "dừng", "🛑 dừng nhắc nhở", "/dung", "/stop"]:
        canceled = await cancel_reminder(chat_id, user.id)
        if canceled:
            await update.message.reply_text(f"🛑 {mention} đã hủy lịch nhắc nhở thành công!", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.", parse_mode="HTML")
        return

    # Xử lý các mốc thời gian
    minutes_map = {
        "10": 10,
        "20": 20,
        "30": 30
    }
    if raw_text in minutes_map:
        await start_reminder_timer(chat_id, user, minutes_map[raw_text], context, update.message)


async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(wait_minutes * 60)

        keyboard = [[InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Lặp lại thông báo mỗi 15 giây (tối đa 15 lần để tránh vi phạm giới hạn spam của Telegram)
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
        logger.info(f"Lịch nhắc cho user {target_user_id} đã được hủy.")
    except Exception as e:
        logger.error(f"Lỗi gửi tin: {e}")


async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng bấm nút OK Inline"""
    query = update.callback_query
    user = query.from_user
    data = query.data

    target_user_id_str = data.split("_")[1]

    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải người đặt lịch này nên không thể bấm tắt!", show_alert=True)
        return

    await query.answer()
    chat_id = query.message.chat_id
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
    # Lắng nghe cả tin nhắn text thường và dữ liệu WebApp
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming_message))

    print("Bot đang chạy...")
    application.run_polling()


if __name__ == "__main__":
    main()

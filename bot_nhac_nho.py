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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay bằng Token mới từ BotFather (hoặc đặt biến môi trường BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN", "9042194702:AAEGuKY5Mq0oaBX_IoEOB9xMsQENktxnhjA")

TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
active_reminders = {}


def get_user_mention(user):
    """Tránh lỗi vỡ tin nhắn khi tên người dùng chứa ký tự đặc biệt"""
    safe_name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{safe_name}</a>'


def get_bottom_keyboard():
    """Bố cục 4 nút đúng chuẩn: 3 nút trên - 1 nút to dài ở dưới"""
    keyboard = [
        [
            KeyboardButton("🟢 10 Phút"),
            KeyboardButton("🟢 20 Phút"),
            KeyboardButton("🟢 30 Phút"),
        ],
        [
            KeyboardButton("🔴 Dừng nhắc nhở")
        ]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,       # Co giãn vừa vặn màn hình điện thoại & máy tính
        is_persistent=True,         # Luôn hiển thị cố định ở chân khung chat
        input_field_placeholder="Bấm nút chọn thời gian hoặc bấm Dừng..."
    )


async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bot Nhắc Đánh Thẻ / Chấm Công</b>\n\n"
        "Vui lòng chọn mốc thời gian bằng các nút bấm bên dưới khung chat:"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_bottom_keyboard(),
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
    """Hủy lịch hẹn của một người dùng cụ thể"""
    key = (chat_id, user_id)
    if key in active_reminders:
        active_reminders[key]["task"].cancel()
        del active_reminders[key]
        return True
    return False


async def start_reminder_timer(chat_id: int, user, minutes: int, context: ContextTypes.DEFAULT_TYPE, message_obj):
    wait_minutes = max(1, minutes - 1)  # Trừ hao nhắc trước 1 phút
    key = (chat_id, user.id)

    await cancel_reminder(chat_id, user.id)

    now_vn = datetime.now(TIMEZONE)
    reminder_time = now_vn + timedelta(minutes=wait_minutes)
    time_str = reminder_time.strftime("%H:%M:%S")
    mention = get_user_mention(user)

    await message_obj.reply_text(
        f"✅ {mention} đã hẹn giờ <b>{minutes} phút</b>.\n"
        f"Bot sẽ nhắc nhở vào lúc: <b>{time_str}</b>",
        parse_mode="HTML"
    )

    task = context.application.create_task(
        reminder_countdown(chat_id, wait_minutes, user.id, mention, context)
    )
    active_reminders[key] = {"task": task}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip().lower()
    # Loại bỏ icon để nhận diện nội dung chính xác
    clean_text = raw_text.replace("🟢", "").replace("🔴", "").replace("🛑", "").strip()

    chat_id = update.effective_chat.id
    user = update.effective_user
    mention = get_user_mention(user)

    # 1. Xử lý nút Dừng hoặc khi gõ chữ 'dừng'
    if clean_text in ["dừng", "dung", "dừng nhắc nhở", "dung nhac nho", "/dung", "/stop"]:
        canceled = await cancel_reminder(chat_id, user.id)
        if canceled:
            await update.message.reply_text(f"🛑 {mention} đã hủy lịch nhắc nhở thành công!", parse_mode="HTML")
        else:
            await update.message.reply_text(f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.", parse_mode="HTML")
        return

    # 2. Xử lý nút bấm 10, 20, 30 phút (hoặc gõ số trực tiếp)
    minutes_map = {
        "10": 10,
        "10 phút": 10,
        "10 phut": 10,
        "20": 20,
        "20 phút": 20,
        "20 phut": 20,
        "30": 30,
        "30 phút": 30,
        "30 phut": 30,
    }

    if clean_text in minutes_map:
        await start_reminder_timer(chat_id, user, minutes_map[clean_text], context, update.message)


async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(wait_minutes * 60)

        keyboard = [[InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Lặp lại nhắc nhở sau mỗi 15 giây (tối đa 15 lần để không bị Telegram giới hạn spam)
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
        logger.error(f"Lỗi gửi tin: {e}")


async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    target_user_id_str = data.split("_")[1]

    # Chỉ người đặt lịch mới có quyền bấm nút OK
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot đang chạy...")
    application.run_polling()


if __name__ == "__main__":
    main()

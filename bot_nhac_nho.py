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

# Điền Token mới từ BotFather vào đây
TOKEN = os.getenv("BOT_TOKEN", "9042194702:AAEGuKY5Mq0oaBX_IoEOB9xMsQENktxnhjA")

# Thiết lập múi giờ Việt Nam an toàn
try:
    TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    from datetime import timezone
    TIMEZONE = timezone(timedelta(hours=7))

# Lưu trữ tiến trình hẹn giờ theo cặp (chat_id, user_id)
active_reminders = {}


def get_user_mention(user):
    """Bọc html.escape để chống lỗi ký tự lạ khi tag tên người dùng"""
    safe_name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{safe_name}</a>'


def get_bottom_keyboard():
    """Giao diện 4 nút chuẩn: 3 nút Xanh bên trên, 1 nút Đỏ to trải dài bên dưới"""
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
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Bấm chọn thời gian hoặc Dừng..."
    )


async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bot Nhắc Đánh Thẻ / Chấm Công</b>\n\n"
        "Vui lòng bấm chọn mốc thời gian bên dưới, hoặc gõ <b>10</b>, <b>20</b>, <b>30</b>, <b>dừng</b>:"
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
    """Hủy hẹn giờ của người dùng cụ thể"""
    key = (chat_id, user_id)
    if key in active_reminders:
        task = active_reminders[key].get("task")
        if task and not task.done():
            task.cancel()
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

    task = asyncio.create_task(
        reminder_countdown(chat_id, wait_minutes, user.id, mention, context)
    )
    active_reminders[key] = {"task": task}


async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt và bóc tách dữ liệu từ mọi nguồn: nút bấm bàn phím, web app, gõ tay"""
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    mention = get_user_mention(user)

    raw_text = ""
    if update.message.web_app_data:
        raw_text = update.message.web_app_data.data.strip()
    elif update.message.text:
        raw_text = update.message.text.strip()

    if not raw_text:
        return

    lower_text = raw_text.lower()
    logger.info(f"Nhận tin nhắn: {raw_text} từ {user.id}")

    try:
        # 1. Bắt lệnh Dừng (dù có emoji 🔴, 🛑 hay gõ chữ dừng, stop, hủy)
        if any(w in lower_text for w in ["dừng", "dung", "stop", "hủy", "huy", "🔴", "🛑"]):
            if not re.search(r'\b(10|20|30)\b', lower_text):
                canceled = await cancel_reminder(chat_id, user.id)
                if canceled:
                    await update.message.reply_text(f"🛑 {mention} đã hủy lịch nhắc nhở thành công!", parse_mode="HTML")
                else:
                    await update.message.reply_text(f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.", parse_mode="HTML")
                return

        # 2. Bắt các số phút 10, 20 hoặc 30 (bắt trúng kể cả '🟢 10 Phút', '10', '10p', '10 phút')
        match = re.search(r'\b(10|20|30)\b', lower_text)
        if match:
            minutes = int(match.group(1))
            await start_reminder_timer(chat_id, user, minutes, context, update.message)
            return

    except Exception as e:
        logger.error(f"Lỗi khi xử lý tin nhắn: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Lỗi hệ thống: {e}")


async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        await asyncio.sleep(wait_minutes * 60)

        keyboard = [[InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Gửi nhắc nhở lặp lại sau mỗi 15 giây (tối đa 15 lần để không vi phạm rate-limit)
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
        logger.info(f"Lịch nhắc của user {target_user_id} đã được hủy.")
    except Exception as e:
        logger.error(f"Lỗi gửi tin trong countdown: {e}")


async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    target_user_id_str = data.split("_")[1]

    # Kiểm tra chỉ người đặt lịch mới có quyền bấm tắt
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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Đã xảy ra ngoại lệ:", exc_info=context.error)


def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming_message))
    application.add_error_handler(error_handler)

    print("Bot đang chạy...")
    application.run_polling()


if __name__ == "__main__":
    main()

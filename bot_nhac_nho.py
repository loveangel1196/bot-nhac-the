import os
import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
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

# Lấy TOKEN từ biến môi trường (hoặc điền Token mới từ BotFather vào đây)
TOKEN = os.getenv("BOT_TOKEN", "DIEN_TOKEN_MOI_CUA_BAN_VAO_DAY")

# Múi giờ Việt Nam (GMT+7)
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Lưu trữ tiến trình: key = (chat_id, user_id)
active_reminders = {}


def get_user_mention(user):
    """Tạo thẻ mention an toàn bằng định dạng HTML"""
    return f'<a href="tg://user?id={user.id}">{user.full_name}</a>'


def get_main_menu_keyboard():
    """Tạo bảng điều khiển trực tiếp trên tin nhắn (hoạt động tốt trong cả nhóm và chat riêng)"""
    keyboard = [
        [
            InlineKeyboardButton("⏱ 10 Phút", callback_data="set_10"),
            InlineKeyboardButton("⏱ 20 Phút", callback_data="set_20"),
            InlineKeyboardButton("⏱ 30 Phút", callback_data="set_30"),
        ],
        [
            InlineKeyboardButton("🛑 Dừng nhắc nhở", callback_data="set_dung")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_menu(chat_id, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Bot Nhắc Đánh Thẻ / Chấm Công</b>\n\n"
        "Bấm chọn mốc thời gian bạn muốn hẹn giờ bên dưới, hoặc gõ <code>dừng</code> để hủy:"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_menu(update.effective_chat.id, context)


async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result:
        new_member = result.new_chat_member
        if new_member.user.id == context.bot.id and new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
            chat_id = update.effective_chat.id
            await asyncio.sleep(1)
            await send_menu(chat_id, context)


async def cancel_reminder(chat_id: int, user_id: int):
    """Hủy lịch hẹn của một người dùng cụ thể trong nhóm"""
    key = (chat_id, user_id)
    if key in active_reminders:
        active_reminders[key]["task"].cancel()
        del active_reminders[key]
        return True
    return False


async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    data = query.data

    await query.answer()

    # Xử lý nút Dừng
    if data == "set_dung":
        canceled = await cancel_reminder(chat_id, user.id)
        mention = get_user_mention(user)
        if canceled:
            await query.message.reply_text(
                f"🛑 {mention} đã hủy lịch nhắc nhở thành công!",
                parse_mode="HTML"
            )
        else:
            await query.message.reply_text(
                f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.",
                parse_mode="HTML"
            )
        return

    # Xử lý các mốc thời gian: 10, 20, 30 phút
    minutes_map = {
        "set_10": (9, 10),
        "set_20": (19, 20),
        "set_30": (29, 30)
    }

    if data in minutes_map:
        wait_minutes, original_minutes = minutes_map[data]
        key = (chat_id, user.id)

        # Hủy lịch cũ nếu người này đã đặt trước đó
        await cancel_reminder(chat_id, user.id)

        now_vn = datetime.now(TIMEZONE)
        reminder_time = now_vn + timedelta(minutes=wait_minutes)
        time_str = reminder_time.strftime("%H:%M:%S")
        mention = get_user_mention(user)

        await query.message.reply_text(
            f"✅ {mention} đã hẹn giờ <b>{original_minutes} phút</b>.\n"
            f"Bot sẽ nhắc nhở vào lúc: <b>{time_str}</b>",
            parse_mode="HTML"
        )

        task = context.application.create_task(
            reminder_countdown(chat_id, wait_minutes, user.id, mention, context)
        )
        active_reminders[key] = {"task": task}


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng gõ chữ 'dừng' hoặc 'dung'"""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    if text in ["dừng", "dung", "/dung", "/stop"]:
        chat_id = update.effective_chat.id
        user = update.effective_user
        canceled = await cancel_reminder(chat_id, user.id)
        mention = get_user_mention(user)

        if canceled:
            await update.message.reply_text(
                f"🛑 {mention} đã hủy lịch nhắc nhở thành công!",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"⚠️ {mention} hiện không có lịch nhắc nào đang chạy.",
                parse_mode="HTML"
            )


async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Hàm đếm ngược và nhắc nhở với tần suất an toàn chống spam Telegram"""
    try:
        await asyncio.sleep(wait_minutes * 60)

        keyboard = [
            [InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Gửi nhắc nhở với chu kỳ 15 giây (tối đa 15 lần để tránh spam vô tận và chặn rate limit)
        for _ in range(15):
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ {user_mention} <b>ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!</b>\n"
                    "Vui lòng bấm nút OK bên dưới để xác nhận hoàn thành."
                ),
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            await asyncio.sleep(15)

    except asyncio.CancelledError:
        logger.info(f"Lịch nhắc của user {target_user_id} tại chat {chat_id} đã được hủy.")
    except Exception as e:
        logger.error(f"Lỗi trong reminder_countdown: {e}")


async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    target_user_id_str = data.split("_")[1]

    # Kiểm tra quyền: chỉ người đặt mới được bấm OK
    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải người đặt lịch này nên không thể bấm tắt!", show_alert=True)
        return

    await query.answer()
    chat_id = query.message.chat_id

    await cancel_reminder(chat_id, user.id)

    mention = get_user_mention(user)
    await query.edit_message_text(
        text=f"👍 <b>{mention} đã đánh thẻ thành công!</b> Đã tắt thông báo nhắc nhở.",
        parse_mode="HTML"
    )


def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))
    application.add_handler(CallbackQueryHandler(handle_button_press, pattern="^set_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("Bot đang chạy...")
    application.run_polling()


if __name__ == "__main__":
    main()

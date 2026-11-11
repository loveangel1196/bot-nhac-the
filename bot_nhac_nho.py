import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ChatMemberHandler, MessageHandler, filters

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay thế bằng Token thật do BotFather cấp
TOKEN = "9042194702:AAEuNzFXtzz27GWq3MMDv9BOHZqhFVg4UxM"

# Múi giờ Việt Nam (GMT+7)
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Lưu trữ tiến trình nhắc nhở theo chat_id
active_reminders = {}

def get_reply_keyboard():
    """Tạo bàn phím nút bấm cố định ở khung nhập chat"""
    keyboard = [
        [KeyboardButton("10 Phút"), KeyboardButton("20 Phút"), KeyboardButton("30 Phút")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_user_mention(user):
    """Lấy định dạng gọi tên chuẩn @username hoặc link profile"""
    if user.username:
        return f"@{user.username}"
    else:
        return f"[{user.full_name}](tg://user?id={user.id})"

async def send_menu(chat_id, context):
    """Gửi tin nhắn kèm bàn phím cố định ở ô chat"""
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng bấm chọn thời gian ở bàn phím bên dưới hoặc gõ `dừng` nếu muốn hủy:",
        reply_markup=get_reply_keyboard(),
        parse_mode="Markdown"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start hoặc /menu"""
    await send_menu(update.effective_chat.id, context)

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tự động gửi menu ngay khi bot được thêm vào nhóm"""
    result = update.my_chat_member
    if result:
        new_member = result.new_chat_member
        if new_member.user.id == context.bot.id and new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
            chat_id = update.effective_chat.id
            await asyncio.sleep(1)
            await send_menu(chat_id, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng bấm nút ở ô chat hoặc nhắn chữ 'dừng'"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip().lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_mention = get_user_mention(user)
    
    # Xử lý lệnh dừng
    if text in ["dừng", "dung"]:
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()
            del active_reminders[chat_id]
            await update.message.reply_text(
                text=f"🛑 **{user_mention}** đã hủy lịch nhắc nhở thành công!",
                parse_mode="Markdown",
                reply_markup=get_reply_keyboard()
            )
        else:
            await update.message.reply_text("⚠️ Hiện tại nhóm không có lịch nhắc nào đang chạy.", reply_markup=get_reply_keyboard())
        return

    minutes_map = {
        "10 phút": (9, 10),
        "20 phút": (19, 20),
        "30 phút": (29, 30),
        "10": (9, 10),
        "20": (19, 20),
        "30": (29, 30)
    }
    
    if text in minutes_map:
        wait_minutes, original_minutes = minutes_map[text]
        
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()

        # Tính toán thời gian cụ thể (Giờ:Phút:Giây)
        now_vn = datetime.now(TIMEZONE)
        reminder_time = now_vn + timedelta(minutes=wait_minutes)
        time_str = reminder_time.strftime("%H:%M:%S")

        await update.message.reply_text(
            text=f"✅ {user_mention} đã đặt hẹn thành công **{original_minutes} phút**.\nBot sẽ nhắc nhở vào lúc: **{time_str}**",
            reply_markup=get_reply_keyboard(),
            parse_mode="Markdown"
        )

        task = context.application.create_task(reminder_countdown(chat_id, wait_minutes, user_id, user_mention, context))
        active_reminders[chat_id] = {'task': task, 'user_id': user_id}

async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
    """Đợi hết thời gian rồi réo tên tài khoản kèm nút OK"""
    try:
        await asyncio.sleep(wait_minutes * 60)
        
        while True:
            keyboard = [
                [InlineKeyboardButton("🚨 OK (XÁC NHẬN ĐÁNH THẺ)", callback_data=f"ok_{target_user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ {user_mention} **ĐÃ ĐẾN GIỜ ĐÁNH THẺ / CLOCK OUT!**\nVui lòng bấm nút OK bên dưới để xác nhận hoàn thành.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Đã hủy lịch nhắc cho chat_id: {chat_id}")

async def acknowledge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiểm tra đúng người được tag mới cho bấm OK"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    target_user_id_str = data.split("_")[1]
    
    if str(user.id) != target_user_id_str:
        await query.answer("⚠️ Bạn không phải là người đặt lịch này nên không thể bấm OK!", show_alert=True)
        return

    await query.answer()
    chat_id = query.message.chat_id
    
    if chat_id in active_reminders:
        active_reminders[chat_id]['task'].cancel()
        del active_reminders[chat_id]
        
    await query.edit_message_text(
        text=f"👍 **{user.full_name} đã đánh thẻ thành công!** Đã tắt nhắc nhở.",
        parse_mode="Markdown"
    )

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký handlers
    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()

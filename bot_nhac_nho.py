import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ChatMemberHandler, MessageHandler, filters

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Thay thế bằng Token thật do BotFather cấp
TOKEN = "9042194702:AAEuNzFXtzz27GWq3MMDv9BOHZqhFVg4UxM"

# Link Web App trên GitHub Pages
WEB_APP_URL = "https://loveangel1196.github.io/bot-nhac-the/"

# Múi giờ Việt Nam (GMT+7)
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Lưu trữ tiến trình nhắc nhở theo chat_id
active_reminders = {}

def get_user_mention(user):
    if user.username:
        return f"@{user.username}"
    else:
        return f"[{user.full_name}](tg://user?id={user.id})"

async def send_menu(chat_id, context):
    keyboard = [
        [InlineKeyboardButton("🎨 Mở bảng chọn thời gian (Mini App)", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="👋 **Nhắc đánh thẻ Bot**\nVui lòng bấm nút bên dưới để mở bảng điều khiển màu sắc, hoặc gõ `dừng` để hủy:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
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

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.web_app_data:
        return
        
    data = update.effective_message.web_app_data.data.strip().lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_mention = get_user_mention(user)

    if data == "dung":
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()
            del active_reminders[chat_id]
            await update.message.reply_text(
                text=f"🛑 **{user_mention}** đã hủy lịch nhắc nhở thành công!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Hiện tại nhóm không có lịch nhắc nào đang chạy.")
        return

    minutes_map = {
        "10": (9, 10),
        "20": (19, 20),
        "30": (29, 30)
    }

    if data in minutes_map:
        wait_minutes, original_minutes = minutes_map[data]
        
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()

        now_vn = datetime.now(TIMEZONE)
        reminder_time = now_vn + timedelta(minutes=wait_minutes)
        time_str = reminder_time.strftime("%H:%M:%S")

        await update.message.reply_text(
            text=f"✅ {user_mention} đã đặt hẹn thành công **{original_minutes} phút**.\nBot sẽ nhắc nhở vào lúc: **{time_str}**",
            parse_mode="Markdown"
        )

        task = context.application.create_task(reminder_countdown(chat_id, wait_minutes, user_id, user_mention, context))
        active_reminders[chat_id] = {'task': task, 'user_id': user_id}

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip().lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_mention = get_user_mention(user)

    if text in ["dừng", "dung"]:
        if chat_id in active_reminders:
            active_reminders[chat_id]['task'].cancel()
            del active_reminders[chat_id]
            await update.message.reply_text(
                text=f"🛑 **{user_mention}** đã hủy lịch nhắc nhở thành công!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Hiện tại nhóm không có lịch nhắc nào đang chạy.")

async def reminder_countdown(chat_id: int, wait_minutes: int, target_user_id: int, user_mention: str, context: ContextTypes.DEFAULT_TYPE):
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

    application.add_handler(CommandHandler(["start", "menu"], start))
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(acknowledge_callback, pattern="^ok_"))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()

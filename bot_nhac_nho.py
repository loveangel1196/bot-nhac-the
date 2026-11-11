import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = "9042194702:AAEuNzFXtzz27GWq3MMDv9BOHZqhFVg4UxM"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Hàm gửi tin nhắn nhắc nhở lặp lại mỗi 5 giây
async def send_repeating_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    data = job.data
    original_message_id = data.get("message_id")
    target_minutes = data.get("target_minutes")

    # Tạo nút OK
    keyboard = [[InlineKeyboardButton("OK", callback_data=f"ack_{job.name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Gửi tin nhắn nhắc nhở kèm nút OK, reply vào tin nhắn gốc của người dùng
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🚨 Này bạn trẻ, nhớ đánh thẻ!!! (Hẹn trước đó {target_minutes} phút)",
        reply_to_message_id=original_message_id,
        reply_markup=reply_markup
    )
    
    # Lưu lại message_id của tin nhắn nhắc nhở này để sau khi bấm OK có thể xóa/sửa nếu cần
    if "reminder_msg_ids" not in context.chat_data:
        context.chat_data["reminder_msg_ids"] = {}
    context.chat_data["reminder_msg_ids"][job.name] = msg.message_id

# Hàm kích hoạt lịch hẹn ban đầu (đợi hết số phút - 1 rồi bắt đầu vòng lặp 5s)
def schedule_initial_timer(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, minutes: int):
    target_minutes = minutes - 1
    delay_seconds = target_minutes * 60 if target_minutes > 0 else 10

    job_name = f"chat_{chat_id}_msg_{message_id}"

    # Đặt hẹn giờ chạy lần đầu tiên sau (target_minutes * 60) giây
    context.job_queue.run_once(
        lambda ctx: start_repeating_loop(ctx, chat_id, message_id, target_minutes, job_name),
        when=delay_seconds,
        name=f"init_{job_name}"
    )
    return target_minutes

# Bắt đầu vòng lặp lặp lại mỗi 5 giây
def start_repeating_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, target_minutes: int, job_name: str):
    # Dùng run_repeating để lặp lại mỗi 5 giây
    job = context.job_queue.run_repeating(
        send_repeating_reminder,
        interval=5.0,  # 5 giây lặp lại 1 lần
        first=0.0,     # Chạy ngay lập tức lần đầu tiên khi hết giờ chờ
        chat_id=chat_id,
        name=job_name,
        data={"message_id": message_id, "target_minutes": target_minutes}
    )

# Lệnh /start hiển thị menu chọn thời gian ban đầu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("10 Phút", callback_data="remind_10"),
            InlineKeyboardButton("20 Phút", callback_data="remind_20"),
            InlineKeyboardButton("30 Phút", callback_data="remind_30"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Vui lòng chọn thời gian nhắc nhở đánh thẻ:", reply_markup=reply_markup
    )

# Xử lý khi bấm nút chọn thời gian (10, 20, 30 phút)
async def time_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("remind_"):
        minutes = int(data.split("_")[1])
        target_mins = schedule_initial_timer(
            context, 
            chat_id=query.message.chat_id, 
            message_id=query.message.message_id, 
            minutes=minutes
        )
        await query.edit_message_text(
            text=f"Đã hẹn! Bot sẽ bắt đầu nhắc đánh thẻ sau {target_mins} phút nữa (cứ 5s nhắc 1 lần nếu chưa bấm OK)."
        )

# Xử lý khi người dùng bấm nút "OK" để tắt nhắc nhở
async def ok_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("ack_"):
        job_name = data.replace("ack_", "")
        
        # Hủy các job đang lặp lại với tên tương ứng
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            
        await query.edit_message_text(text="✅ Đã ghi nhận đánh thẻ! Đã tắt nhắc nhở.")

# Xử lý khi nhắn tin số trực tiếp "10", "20", "30"
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text in ["10", "20", "30"]:
        minutes = int(text)
        target_mins = schedule_initial_timer(
            context, 
            chat_id=update.message.chat_id, 
            message_id=update.message.message_id, 
            minutes=minutes
        )
        await update.message.reply_text(
            f"Đã nhận! Bot sẽ nhắc bạn đánh thẻ sau {target_mins} phút nữa (lặp lại mỗi 5s nếu chưa bấm OK)."
        )

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    
    # Xử lý các callback nút bấm
    application.add_handler(CallbackQueryHandler(ok_button_handler, pattern="^ack_"))
    application.add_handler(CallbackQueryHandler(time_button_handler, pattern="^remind_"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    print("Bot đang chạy...")
    application.run_polling()

if __name__ == "__main__":
    main()
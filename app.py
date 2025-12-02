from flask import Flask, request
import os
from dotenv import load_dotenv
import google.generativeai as genai
import logging
import threading
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import qrcode
from io import BytesIO
import base64

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model
model = genai.GenerativeModel('gemini-pro')

class WhatsAppBot:
    def __init__(self):
        self.driver = None
        self.is_authenticated = False
        self.running = False
        
    def initialize_driver(self):
        """Initialize Chrome driver for WhatsApp Web"""
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--disable-gpu')
        
        # For Heroku compatibility
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
        
        self.driver = webdriver.Chrome(
            options=chrome_options,
            service_log_path=os.devnull
        )
        self.driver.get("https://web.whatsapp.com")
        logger.info("WhatsApp Web opened")
        
    def wait_for_login(self):
        """Wait for user to scan QR code"""
        try:
            # Wait for QR code to appear
            qr_element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label='Scan me!']"))
            )
            
            # Generate QR code from canvas
            qr_base64 = self.driver.execute_script("""
                var canvas = arguments[0];
                return canvas.toDataURL('image/png').substring(22);
            """, qr_element)
            
            # Display QR code in terminal
            qr_img = qrcode.make(base64.b64decode(qr_base64))
            qr_img.show()
            logger.info("QR code generated. Please scan with WhatsApp")
            
            # Wait for login to complete
            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='chat-list']"))
            )
            
            self.is_authenticated = True
            logger.info("WhatsApp login successful!")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def get_gemini_response(self, message):
        """Get response from Gemini AI"""
        try:
            response = model.generate_content(message)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "I'm having trouble connecting to the AI service. Please try again later."
    
    def process_messages(self):
        """Continuously check for new messages"""
        while self.running:
            try:
                # Find unread messages
                unread_chats = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    "div[aria-label='Unread']"
                )
                
                for chat in unread_chats:
                    chat.click()
                    time.sleep(2)
                    
                    # Get the last message
                    messages = self.driver.find_elements(
                        By.CSS_SELECTOR, 
                        "div[class*='message-in'], div[class*='message-out']"
                    )
                    
                    if messages:
                        last_message = messages[-1]
                        message_text = last_message.text
                        
                        # Check if message is from someone else
                        if "message-in" in last_message.get_attribute("class"):
                            # Get AI response
                            ai_response = self.get_gemini_response(message_text)
                            
                            # Send response
                            input_box = self.driver.find_element(
                                By.CSS_SELECTOR, 
                                "div[contenteditable='true'][data-tab='10']"
                            )
                            input_box.click()
                            input_box.send_keys(ai_response)
                            input_box.send_keys("\n")
                            
                            logger.info(f"Message processed: {message_text[:50]}...")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error processing messages: {e}")
                time.sleep(10)
    
    def start(self):
        """Start the WhatsApp bot"""
        self.running = True
        self.initialize_driver()
        
        if self.wait_for_login():
            # Start message processing in a separate thread
            processing_thread = threading.Thread(target=self.process_messages)
            processing_thread.daemon = True
            processing_thread.start()
            logger.info("WhatsApp bot started successfully!")
            return True
        return False
    
    def stop(self):
        """Stop the WhatsApp bot"""
        self.running = False
        if self.driver:
            self.driver.quit()
        logger.info("WhatsApp bot stopped")

# Global bot instance
bot = WhatsAppBot()

@app.route('/')
def home():
    return "WhatsApp Gemini Bot is running!"

@app.route('/start', methods=['POST'])
def start_bot():
    """Endpoint to start the bot"""
    if bot.start():
        return {"status": "success", "message": "Bot started successfully"}
    return {"status": "error", "message": "Failed to start bot"}

@app.route('/stop', methods=['POST'])
def stop_bot():
    """Endpoint to stop the bot"""
    bot.stop()
    return {"status": "success", "message": "Bot stopped successfully"}

@app.route('/health', methods=['GET'])
def health_check():
    return {"status": "healthy", "bot_running": bot.running}

def run_bot_in_background():
    """Run bot in background thread"""
    time.sleep(10)  # Wait for Flask to start
    if os.getenv("AUTO_START", "true").lower() == "true":
        bot.start()

if __name__ == '__main__':
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot_in_background)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

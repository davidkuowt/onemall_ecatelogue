from flask import Flask, render_template, request, jsonify
import requests
import json
import jwt
import time
import os
from datetime import datetime, timezone

app = Flask(__name__)

class MMSAPIClient:
    def __init__(self):
        # Load credentials from environment variables (secure for production)
        self.store_code = os.environ.get('STORE_CODE')
        self.uuid = os.environ.get('API_UUID') 
        self.private_key = os.environ.get('PRIVATE_KEY')
        self.host = "https://mms-api.shoalter.com/mmsAdmin"
        
        if not all([self.store_code, self.uuid, self.private_key]):
            raise ValueError("Missing required environment variables: STORE_CODE, API_UUID, PRIVATE_KEY")
    
    def generate_token(self):
        """Generate JWT token for API authentication"""
        current_timestamp = int(time.time())
        
        payload = {
            "sub": "shoalter",
            "name": "shoalter", 
            "iat": current_timestamp,
            "x-api-key": self.uuid
        }
        
        # Format private key properly
        if not self.private_key.startswith('-----BEGIN'):
            formatted_key = f"-----BEGIN PRIVATE KEY-----\n{self.private_key}\n-----END PRIVATE KEY-----"
        else:
            formatted_key = self.private_key.replace('\\n', '\n')
        
        token = jwt.encode(payload, formatted_key, algorithm='RS256')
        return token
    
    def get_product(self, sku_code):
        """Fetch product details from MMS API"""
        try:
            token = self.generate_token()
            
            headers = {
                'Content-Type': 'application/json',
                'x-auth-token': token,
                'storeCode': self.store_code,
                'platformCode': 'HKTV',
                'businessType': 'eCommerce'
            }
            
            payload = [{"skuCode": sku_code}]
            
            response = requests.post(
                f"{self.host}/oapi/api/product/details",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 'success' and data.get('data'):
                    product_data = data['data'][0]
                    return self.format_product_data(product_data)
                else:
                    return None
            else:
                print(f"API Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error fetching product: {str(e)}")
            return None
    
    def format_product_data(self, product_data):
        """Format product data for frontend"""
        # Get main image
        main_image = None
        if product_data.get('imagesMainPhotoList'):
            main_image = product_data['imagesMainPhotoList'][0].get('filePath')
        
        # Format price
        original_price = product_data.get('originalPrice', 0)
        selling_price = product_data.get('sellingPrice')
        currency = product_data.get('currencyCode', 'HKD')
        
        if selling_price and selling_price != original_price:
            price_text = f"{currency} ${selling_price} (原價: {currency} ${original_price})"
        else:
            price_text = f"{currency} ${original_price}"
        
        return {
            'skuCode': product_data.get('fullSkuCode'),
            'title': product_data.get('skuNameTchi') or product_data.get('skuName'),
            'titleEn': product_data.get('skuName'),
            'description': product_data.get('skuSDescCh') or product_data.get('skuSDescEn'),
            'price': price_text,
            'originalPrice': original_price,
            'sellingPrice': selling_price,
            'currency': currency,
            'image': main_image,
            'brand': product_data.get('brandNameTc') or product_data.get('brandNameEn'),
            'category': product_data.get('primaryCategoryCode'),
            'barcode': product_data.get('barcode')
        }

# Initialize API client
try:
    api_client = MMSAPIClient()
except ValueError as e:
    print(f"Configuration Error: {e}")
    api_client = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/product', methods=['POST'])
def get_product():
    if not api_client:
        return jsonify({
            'success': False, 
            'error': '伺服器配置錯誤，請聯絡管理員'
        }), 500
    
    try:
        data = request.get_json()
        sku_code = data.get('skuCode', '').strip()
        
        if not sku_code:
            return jsonify({
                'success': False,
                'error': '請輸入產品SKU代碼'
            }), 400
        
        product = api_client.get_product(sku_code)
        
        if product:
            return jsonify({
                'success': True,
                'product': product
            })
        else:
            return jsonify({
                'success': False,
                'error': '找不到該產品，請檢查SKU代碼是否正確'
            }), 404
            
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': '系統發生錯誤，請稍後再試'
        }), 500

@app.route('/product/<sku_code>')
def product_detail(sku_code):
    """Product detail page for sharing"""
    if not api_client:
        return "系統錯誤", 500
        
    product = api_client.get_product(sku_code)
    if product:
        return render_template('product_detail.html', product=product)
    else:
        return "找不到產品", 404

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
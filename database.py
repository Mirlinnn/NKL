# database.py
async def create_order(order_id, user_id, service, quantity, price, link):
    # Вставить с order_id как строку
    await pool.execute("INSERT INTO orders (order_id, user_id, service, quantity, price, link, status) VALUES (?, ?, ?, ?, ?, ?, 'NEW')",
                       (order_id, user_id, service, quantity, price, link))

async def get_order(order_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM orders WHERE order_id = ?", order_id)

async def update_order_status(order_id, status, comment=None):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE orders SET status = ?, comment = ? WHERE order_id = ?", status, comment, order_id)
class DataManager:
    def __init__(self):
        # 定义钩子仓库，用来存放注册进来的函数
        self.hooks = {
            "before_save": [],
            "after_save": []
        }

    def register_hook(self, event_type, callback_function):
        """允许外部注册钩子"""
        if event_type in self.hooks:
            self.hooks[event_type].append(callback_function)
            print(f"[系统] 注册了一个 '{event_type}' 钩子")

    def save_data(self, data):
        print(f"\n[系统] 开始处理数据: {data}")

        # 1. 触发 'before_save' 钩子 (允许修改数据)
        processed_data = data
        for hook in self.hooks["before_save"]:
            # 将数据传给钩子，并接收钩子处理后的返回值
            processed_data = hook(processed_data)
        
        # 模拟核心保存逻辑
        print(f"[系统] 正在将数据写入数据库: {processed_data}")

        # 2. 触发 'after_save' 钩子 (通常用于通知)
        for hook in self.hooks["after_save"]:
            hook(processed_data)
        
        print("[系统] 流程结束。\n")

# --- 外部开发者使用部分 ---

def main():
    manager = DataManager()

    # 定义一个钩子：用于数据清洗（把文本变大写）
    def clean_data_hook(data):
        print("  -> [Hook执行] 数据清洗钩子被触发: 转为大写")
        return data.upper()

    # 定义一个钩子：用于发送通知
    def send_email_hook(data):
        print(f"  -> [Hook执行] 通知钩子被触发: 已发送邮件告知数据 '{data}' 已保存")

    # 注册钩子
    manager.register_hook("before_save", clean_data_hook)
    manager.register_hook("after_save", send_email_hook)

    # 运行主程序
    manager.save_data("hello world")

if __name__ == "__main__":
    main()

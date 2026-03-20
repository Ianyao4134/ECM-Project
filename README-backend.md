# ECM Thinking Engine (Backend MVP)

一个 Python Web 后端（Flask + Waitress），用于运行 **多阶段 ECM 思考系统**，通过 **DeepSeek API** 生成各阶段输出，并从输出中解析 `tags / quotes / hooks`，写入 `data/notes.json`。

## 目录结构

- `app/`：后端代码
- `prompts/`：各模块提示词（txt）
- `data/notes.json`：解析后的笔记数据

## 运行

1) 进入目录：

```bash
cd "C:\Users\lulina\Desktop\ECM V2.1\ecm_backend"
```

2) 创建虚拟环境并安装依赖：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

3) 配置环境变量（不要写死在代码里）：

在本目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_MODEL=deepseek-chat
```

4) 启动：

```bash
.venv\Scripts\python -m app.main
```

服务地址：`http://127.0.0.1:9000`

## 调用

POST `http://127.0.0.1:9000/ecm/run`

```json
{
  "topic": "可选：主题",
  "question": "用户输入问题"
}
```

## 用户登录与项目管理（MVP）

后台提供了一个**本机使用**的轻量级登录与项目管理模块，用于配合前端保存每次对话与笔记状态。

### 1. 接口一览（均已通过 Vite 代理到 `/ecm/...`）

- `POST /ecm/auth/login`  
  - 说明：登录或注册（如果用户名不存在则自动创建）。  
  - Body：

    ```json
    {
      "username": "your_name",
      "password": "your_password"
    }
    ```

  - 返回示例：

    ```json
    {
      "id": "user-uuid",
      "username": "your_name"
    }
    ```

- `GET /ecm/projects/list?userId=<user-id>`  
  - 说明：列出该用户的历史项目。  
  - 返回示例：

    ```json
    [
      { "id": "proj-1", "name": "项目 A", "updatedAt": 1731300000 },
      { "id": "proj-2", "name": "项目 B", "updatedAt": 1731200000 }
    ]
    ```

- `POST /ecm/projects/save`  
  - 说明：保存当前项目（新建或更新）。  
  - Body：

    ```json
    {
      "userId": "user-uuid",
      "projectId": "可选，已有项目的 id；为空则新建",
      "name": "项目名称",
      "state": {
        "chats": { "...": "前端序列化的对话状态" },
        "noteText": "Function 3 笔记内容"
      }
    }
    ```

  - 返回示例：

    ```json
    {
      "id": "proj-1",
      "name": "项目名称",
      "updatedAt": 1731301234
    }
    ```

- `GET /ecm/projects/load?userId=<user-id>&projectId=<project-id>`  
  - 说明：加载某个历史项目的完整 state，供前端恢复界面。  
  - 返回示例：

    ```json
    {
      "id": "proj-1",
      "name": "项目名称",
      "state": {
        "chats": { "...": "前端序列化的对话状态" },
        "noteText": "Function 3 笔记内容"
      }
    }
    ```

### 2. 数据落盘位置

- `data/users.json`：保存**本机用户列表**，字段示例：

  ```json
  [
    { "id": "user-uuid", "username": "your_name", "password": "明文密码（仅本机开发用）" }
  ]
  ```

- `data/projects.json`：保存**每个用户的项目**：

  ```json
  [
    {
      "id": "proj-uuid",
      "userId": "user-uuid",
      "name": "项目名称",
      "createdAt": 1731200000,
      "updatedAt": 1731300000,
      "state": { "...": "前端自定义的状态结构" }
    }
  ]
  ```

> 注意：这是一个方便本机使用的 MVP 方案，因此密码明文存储、无加密/权限控制，**不要用于生产环境或多人共享服务器**。



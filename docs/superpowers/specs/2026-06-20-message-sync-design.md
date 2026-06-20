# 消息同步系统设计

日期：2026-06-20

## 背景

项目从空仓库开始实现一个基于 Python 后端的消息同步系统。目标是部署在 Ubuntu VPS 上，代码尽量简洁、小型，支持多用户通过网页注册登录后保存和访问自己的消息。

## 已确认需求

- 使用 `FastAPI + SQLite + Jinja2`。
- 支持开放注册和多用户登录。
- 每个用户只能查看、下载、删除自己发送的消息。
- 登录后可发送文本、文件、图片。
- 单个上传文件最大 `20MB`。
- 发送消息时可设置自动删除时间：不自动删除、`1`、`5`、`10`、`30`、`60` 分钟。
- 到期后真正删除数据库记录和上传文件。
- 只需要网页登录使用，不额外提供公开 API。
- 提供 Ubuntu VPS 可直接执行的部署脚本。

## 非目标

- 不实现邀请码注册。
- 不默认配置域名和 HTTPS。
- 不引入 Celery、Redis、PostgreSQL 等额外服务。
- 不实现跨用户共享消息。
- 不实现移动端 App 或独立客户端。

## 技术方案

采用 `FastAPI + SQLite + Jinja2`：

- `FastAPI` 负责 HTTP 路由、表单提交、文件上传和响应。
- `SQLite` 作为单文件数据库，减少 VPS 运维成本。
- `Jinja2` 渲染服务端页面，避免引入前端构建链。
- 本地文件系统保存上传文件和图片。
- `systemd` 管理应用服务和定时清理。
- `nginx` 反向代理到本地 `uvicorn` 服务。

这个方案优先满足“小、简单、能直接部署”的目标。它适合自用或小规模多用户场景；如果未来并发和数据规模明显增大，再迁移到 PostgreSQL。

## 项目结构

```text
app/
  main.py
  db.py
  auth.py
  messages.py
  templates/
    base.html
    login.html
    register.html
    index.html
  static/
    style.css
tests/
  test_auth.py
  test_messages.py
requirements.txt
deploy_ubuntu.sh
README.md
```

职责划分：

- `app/main.py`：应用入口、路由注册、启动时初始化数据库。
- `app/db.py`：SQLite 连接、建表、基础数据库工具。
- `app/auth.py`：注册、登录、退出、密码哈希、当前用户校验。
- `app/messages.py`：消息创建、列表、下载、手动删除、过期清理。
- `app/templates/`：服务端页面模板。
- `app/static/`：少量 CSS。
- `tests/`：核心行为测试。

运行时上传文件默认保存到 `uploads/`。该目录不提交到 git。

## 数据模型

`users` 表：

- `id`
- `username`，唯一
- `password_hash`
- `created_at`

`messages` 表：

- `id`
- `user_id`
- `kind`：`text`、`file`、`image`
- `content`
- `original_filename`
- `stored_filename`
- `mime_type`
- `size_bytes`
- `expires_at`
- `created_at`

`expires_at` 为空表示不自动删除。

## 权限规则

- 未登录用户只能访问登录页、注册页和静态资源。
- 登录后只能查询 `user_id = 当前用户 id` 的消息。
- 下载文件前必须校验消息归属。
- 删除消息前必须校验消息归属。
- 注册为开放注册，用户名唯一。
- 密码只保存哈希，不保存明文。

如果发送表单同时包含文本和上传文件，系统会创建两条消息：一条文本消息、一条文件或图片消息。这样页面展示直观，代码也保持简单。

## 页面和路由

- `GET /register`：注册页。
- `POST /register`：提交注册。
- `GET /login`：登录页。
- `POST /login`：提交登录。
- `POST /logout`：退出登录。
- `GET /`：消息页。
- `POST /messages`：创建文本、文件或图片消息。
- `GET /messages/{id}/download`：下载当前用户自己的文件或图片。
- `POST /messages/{id}/delete`：删除当前用户自己的消息。
- `POST /cleanup`：本地定时清理接口。

消息页包含：

- 文本输入框。
- 文件上传控件。
- 自动删除下拉框：不自动删除、`1`、`5`、`10`、`30`、`60` 分钟。
- 当前用户自己的消息列表。
- 文件大小、创建时间、过期时间、下载按钮、删除按钮。

## 上传和存储

- 单个上传最大 `20MB`。
- 文件和图片共用上传限制。
- 图片通过 `mime_type` 判断并标记为 `image`，普通文件标记为 `file`。
- 存储文件名使用随机值，避免用户上传文件名冲突或路径穿越。
- 下载时返回原始文件名。
- 删除消息时同步删除对应本地文件。

## 过期删除

过期删除不引入额外队列服务：

- 每次访问消息页、发送消息、下载消息前，先执行一次轻量清理。
- 清理逻辑删除所有 `expires_at <= 当前时间` 的消息。
- 如果消息有上传文件，同步删除本地文件。
- 部署脚本配置 `systemd timer`，每分钟调用一次本地清理接口，避免无人访问时文件长期保留。
- 清理接口使用 `CLEANUP_TOKEN` 校验，或仅允许本机定时任务访问。

## 配置

通过 `.env` 配置：

- `SECRET_KEY`
- `DATABASE_PATH`
- `UPLOAD_DIR`
- `MAX_UPLOAD_MB=20`
- `CLEANUP_TOKEN`
- `HOST=127.0.0.1`
- `PORT=8000`

开发环境可直接读取默认配置。生产环境由部署脚本生成 `.env`。

## 测试计划

核心测试覆盖：

- 注册成功。
- 重复用户名注册失败。
- 登录成功。
- 错误密码登录失败。
- 未登录不能访问消息页。
- 用户 A 看不到用户 B 的消息。
- 用户 A 下载不了用户 B 的文件。
- 用户 A 删除不了用户 B 的消息。
- 文本消息创建成功。
- 文件大小超过 `20MB` 被拒绝。
- 自动删除时间只允许不设置、`1`、`5`、`10`、`30`、`60` 分钟。
- 过期清理会删除数据库记录和本地文件。

实现时按测试先行处理核心行为。

## 部署脚本设计

`deploy_ubuntu.sh` 面向 Ubuntu VPS：

1. 安装系统依赖：`python3-venv`、`python3-pip`、`nginx`。
2. 创建应用目录：`/opt/online_msg_forward`。
3. 创建 Python 虚拟环境。
4. 安装 `requirements.txt`。
5. 写入生产 `.env`。
6. 创建上传目录。
7. 创建 `systemd` 服务，用 `uvicorn` 启动应用。
8. 配置 `nginx` 反向代理到本地应用端口。
9. 配置 `systemd timer` 每分钟调用清理接口。
10. 重启服务并输出访问地址和常用命令。

脚本默认通过服务器 IP 访问，不默认申请证书。HTTPS 和域名配置留到后续明确需求时再加。

## 成功标准

- 本地测试通过。
- 用户可以注册、登录、退出。
- 登录用户可以创建文本消息、上传文件、上传图片。
- 用户只能访问自己的消息。
- 到期消息和文件会被真实删除。
- Ubuntu VPS 上执行部署脚本后能启动服务并通过浏览器访问。

# online_msg_forward

一个小型消息同步系统，基于 FastAPI + SQLite + Jinja2。

## 功能

- 可配置开放注册、登录、退出。
- 用户只能查看、下载、删除自己的消息。
- 支持文本、文件、图片。
- 单个上传最大 20MB。
- 自动删除时间支持：不删除、1、5、10、30、60 分钟。
- 到期后删除数据库记录和本地文件。

## 本地运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

默认访问：`http://127.0.0.1:8000`

## 配置

可通过 `.env` 或环境变量配置：

```env
SECRET_KEY=change-me
DATABASE_PATH=data/app.db
UPLOAD_DIR=uploads
MAX_UPLOAD_MB=20
ALLOW_REGISTRATION=true
CLEANUP_TOKEN=change-me
HOST=127.0.0.1
PORT=8000
```

`ALLOW_REGISTRATION=false` 时，登录页不显示注册入口，`/register` 页面和提交接口都会关闭。

## 测试

```bash
python -m pytest -q
```

## Ubuntu VPS 部署

在服务器上进入项目目录后执行：

```bash
sudo bash deploy_ubuntu.sh
```

脚本会：

- 安装 `python3-venv` 和 `python3-pip`。
- 如果服务正在运行，先停止 `online_msg_forward.service` 和清理 timer。
- 在当前项目目录创建 `.venv`、`data/`、`uploads/`。
- 如果 `.env` 不存在则创建；如果 `.env` 已存在则保留，不覆盖已有配置。
- 创建并启动 `online_msg_forward.service`。
- 创建每分钟运行一次的过期清理 timer。

脚本不会删除或重置 `data/` 和 `uploads/`，重复执行部署不会清空已有数据库和上传文件。

脚本不会复制代码到 `/opt`，也不会安装或修改 `nginx`，不会配置域名或 HTTPS。你可以自行把 `nginx` 反向代理到脚本输出的本地监听地址，默认是 `http://127.0.0.1:8000`。

常用命令：

```bash
systemctl status online_msg_forward.service
journalctl -u online_msg_forward.service -f
systemctl status online_msg_forward-cleanup.timer
```

# QingdaoU OnlineJudge 比赛题目导出

## 安装（Python 3.9 及以上）

```powershell
python -m pip install -r requirements.txt
```

## 使用

```powershell
python export_contest.py
```

输入完整比赛网址（如 `https://oj.example.com/contest/123`）及比赛密码；没有密码直接回车。在弹出的浏览器里正常登录后，回到终端按回车。浏览器登录状态保存在用户目录下的 `.qduoj-export-browser` 中，之后有效时无需再次登录。会话过期后重新登录即可；此目录包含登录状态，请勿分享，删除该目录可清除会话。

脚本使用电脑上安装的 Microsoft Edge，无需下载 Playwright 的 Chromium。请确保已安装 Edge。脚本使用独立的浏览器配置目录，因此首次使用仍需登录。

脚本在运行目录下创建“比赛名称_比赛ID”目录，Markdown 和 `images` 子目录都在其中。同一比赛再次运行会覆盖同名 Markdown 和同地址图片。支持标准 QingdaoU OnlineJudge 2.0 接口，学校修改接口或认证方式时可能需要调整；请使用有权访问比赛的账号，题目须已对账号开放。导出图片失败时会列出地址并以非零状态退出，Markdown 保留原图地址。Markdown 中数学公式的显示依赖所使用的阅读器支持 LaTeX。

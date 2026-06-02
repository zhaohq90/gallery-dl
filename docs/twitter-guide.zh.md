# gallery-dl 导出 Twitter/X 用户内容指南

## 1. 获取 Cookies（必需步骤）

Twitter/X 已不再支持用户名密码登录，**必须使用 Cookies 进行认证**。gallery-dl 只需要一个关键的 Cookie：`auth_token`。

### 方法一：从浏览器导出（推荐）

使用浏览器插件导出 Netscape 格式的 `cookies.txt`：

- **Chrome / Edge**: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox**: [Export Cookies](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)

操作步骤：
1. 在浏览器中登录 x.com
2. 点击插件图标，导出 `cookies.txt`
3. 将文件保存到本地，例如 `~/twitter-cookies.txt`

### 方法二：直接从浏览器提取

gallery-dl 支持直接从浏览器配置文件中提取 Cookies：

```bash
# 从 Firefox 提取
gallery-dl --cookies-from-browser firefox "https://x.com/USERNAME"

# 从 Chrome 提取
gallery-dl --cookies-from-browser chrome "https://x.com/USERNAME"

# 从 Safari 提取 (macOS)
gallery-dl --cookies-from-browser safari "https://x.com/USERNAME"
```

### 方法三：手动配置 Cookies

从浏览器开发者工具中获取 `auth_token` 值，写入配置文件：

1. 打开 x.com，按 F12 打开开发者工具
2. 进入 Application（应用程序）→ Cookies → `https://x.com`
3. 找到 `auth_token`，复制其值
4. 在配置文件中设置：

```json
{
    "extractor": {
        "twitter": {
            "cookies": {
                "auth_token": "你的auth_token值"
            }
        }
    }
}
```

### 方法四：命令行指定 cookies 文件

```bash
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/USERNAME"
```

---

## 2. 用户内容提取模式

通过 URL 路径决定提取哪些内容：

| URL 模式 | 提取内容 | 说明 |
|---|---|---|
| `https://x.com/USER` | 用户主页（默认时间线） | 由 `include` 配置控制具体提取哪些内容 |
| `https://x.com/USER/timeline` | 时间线推文 | 由 `timeline.strategy` 控制策略 |
| `https://x.com/USER/tweets` | 纯推文（不含回复和转推） | 对应网页上的 Tweets 标签 |
| `https://x.com/USER/with_replies` | 推文+回复 | 包含该用户的所有回复 |
| `https://x.com/USER/media` | 媒体推文 | 仅包含带图片/视频的推文 |
| `https://x.com/USER/likes` | 点赞内容 | 需要登录，仅自己可见 |
| `https://x.com/i/bookmarks` | 书签内容 | 需要登录，仅自己可见 |
| `https://x.com/USER/highlights` | 精选内容 | 需要登录 |
| `https://x.com/USER/following` | 正在关注列表 | 用户信息，非推文 |
| `https://x.com/USER/followers` | 粉丝列表 | 用户信息，非推文 |
| `https://x.com/USER/status/TWEET_ID` | 单条推文 | — |
| `https://x.com/USER/status/TWEET_ID/quotes` | 引用该推文的内容 | — |
| `https://x.com/USER/info` | 用户信息 | 仅元数据，不含推文 |
| `https://x.com/USER/photo` | 头像 | 仅下载头像 |
| `https://x.com/USER/header_photo` | 主页背景图 | 仅下载背景图 |
| `https://x.com/hashtag/TAG` | 话题标签搜索 | — |
| `https://x.com/search?q=QUERY` | 搜索 | 支持高级搜索语法 |
| `https://x.com/home` | 主页时间线 | "为你推荐"或"正在关注" |
| `https://x.com/i/lists/LIST_ID` | 列表时间线 | — |
| `https://x.com/i/lists/LIST_ID/members` | 列表成员 | 用户信息 |
| `https://x.com/i/communities/COMMUNITY_ID` | 社区内容 | — |

---

## 3. 全部配置选项

以下选项在配置文件的 `"extractor": {"twitter": { ... }}` 中设置，或通过 `-o` 命令行参数指定。

### 内容过滤

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `retweets` | `bool` / `"original"` | `false` | 是否包含转推。`"original"` 使用原推数据替代转推元数据 |
| `replies` | `bool` / `"self"` | `true` | 是否包含回复。`"self"` 仅包含回复自己的推文 |
| `pinned` | `bool` | `false` | 是否包含置顶推文的媒体 |
| `quoted` | `bool` | `false` | 是否获取引用推文中的媒体 |
| `ads` | `bool` | `false` | 是否获取推广/广告推文中的媒体 |
| `text-tweets` | `bool` | `false` | 是否保留纯文本推文（默认只下载含媒体的推文） |

### 媒体下载

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `videos` | `bool` / `"ytdl"` | `true` | 视频下载：`true` 下载最高比特率版本，`"ytdl"` 使用 yt-dlp 下载，`false` 跳过视频 |
| `previews` | `bool` | `false` | 是否下载视频预览图 |
| `cards` | `bool` / `"ytdl"` | `false` | 是否处理 Twitter Card（如链接预览卡片中的图片/视频） |
| `cards-blacklist` | `list` | — | 要忽略的卡片类型/域名，如 `["youtube.com"]` |
| `twitpic` | `bool` | `false` | 是否提取 TwitPic 嵌入图片 |
| `size` | `list` | `["orig", "4096x4096", "large", "medium", "small"]` | 图片尺寸优先级列表，从前到后依次回退 |
| `unavailable` | `bool` | `false` | 尝试下载标记为"不可用"的媒体（如地域限制内容） |

### 文章处理

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `articles` | `bool` / `string` / `list` | `true` | 文章推文处理：`true` 全部启用，此外可选子项 `cover`、`media`、`html`、`metadata`/`meta`、`document`/`doc` |

### 抓取数量与分页

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `limit` | `int` / `list` | `50` | 每次 API 请求获取的结果数（对时间线等有效）。可以是一个递减列表，如 `[50, 20, 10]`，空结果时自动降级 |
| `search-limit` | `int` / `list` | `20` | 每次搜索请求的结果数 |
| `search-stop` | `int` | `3` | 连续空结果批次数，达到后停止搜索 |
| `cursor` | `bool` / `string` | `true` | 断点续传：`true` 从头开始并在中断时记录游标，`false` 从头开始不记录，任意字符串从指定游标恢复 |

### 搜索选项

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `search-results` | `string` | `"latest"` | 搜索结果排序：`"top"`（热门）、`"latest"`/`"live"`（最新）、`"media"`（媒体） |
| `search-pagination` | `string` | `"max_id"` | 搜索翻页方式：`"cursor"`（游标翻页）、`"max_id"`/`"id"`（ID 翻页）、`"until"`/`"date"`/`"dt"`（日期翻页） |

### 用户主页行为

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `include` | `string` / `list` | `"timeline"` | 访问用户主页 URL 时提取的子类别。可选值：`info`、`avatar`、`background`、`timeline`、`tweets`、`media`、`with-replies`、`highlights`、`likes`，或 `"all"` 全部提取 |
| `timeline.strategy` | `string` | `"auto"` | 时间线策略：`"tweets"`（仅推文）、`"media"`（仅媒体）、`"with_replies"`（含回复）、`"auto"`（根据 retweets/text-tweets 设置自动选择） |

### 认证与会话

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `cookies` | `string` / `object` / `list` | — | Cookies 来源：cookies.txt 路径、cookie 键值对、浏览器配置 `["firefox"]` |
| `csrf` | `string` | `"cookies"` | CSRF token 处理：`"auto"` 自动生成，`"cookies"` 使用 cookie 中的 `ct0` |
| `logout` | `bool` | `false` | 访问受阻时退出登录以游客身份重试 |
| `locked` | `string` | `"abort"` | 账户临时锁定处理：`"abort"` 中止，`"wait"` 等待 |
| `ratelimit` | `string` | `"wait"` | 速率限制处理：`"abort"`、`"abort:N"`、`"wait"`、`"wait:N"`（N 为最大等待秒数） |
| `retries-api` | `int` | `9` | API 服务器错误最大重试次数，`-1` 无限重试 |

### 单条推文

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `tweet-endpoint` | `string` | `"auto"` | 单推文 API 端点：`"restid"`（游客可用）、`"detail"`（更稳定，需登录）、`"auto"`（登录时用 detail，游客用 restid） |
| `conversations` | `bool` / `"accessible"` | `false` | 获取单推文的完整对话线程 |
| `expand` | `bool` | `false` | 将每条推文展开为完整对话线程（每条推文额外 1+ 次 API 调用） |

### 其他

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `transform` | `bool` | `true` | 是否将推文/用户元数据转换为统一格式 |
| `unique` | `bool` | `true` | 是否去重（忽略已见过的推文） |
| `metadata-user` | `bool` | `false` | 提取扩展用户元数据（based_in、friends_mutual 等，每个用户额外 2 次请求） |
| `users` | `string` | `"user"` | following/list-members 查询中用户 URL 的格式：`"user"`、`"timeline"`、`"tweets"`、`"media"` 或自定义格式字符串 |

---

## 4. 常用命令示例

### 基本下载

```bash
# 下载用户的所有媒体推文（不含转推）
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"

# 下载用户的时间线（包含回复，不含转推）
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/timeline"

# 下载用户推文（纯推文，不含回复和转推）
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/tweets"
```

### 控制下载数量

```bash
# 每次 API 请求获取 20 条（减少每次请求量）
gallery-dl -o "limit=20" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"

# 搜索每次获取 10 条
gallery-dl -o "search-limit=10" --cookies ~/twitter-cookies.txt "https://x.com/search?q=from:USERNAME"
```

### 包含转推和回复

```bash
# 包含转推
gallery-dl -o "retweets=true" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"

# 包含转推但使用原推信息
gallery-dl -o "retweets=original" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"

# 仅包含回复自己的推文
gallery-dl -o "replies=self" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/timeline"

# 不包含任何回复
gallery-dl -o "replies=false" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/timeline"
```

### 保留纯文本推文

```bash
# 默认情况下只下载含媒体的推文，如需保留纯文本推文（配合 exec/postprocessors 使用）
gallery-dl -o "text-tweets=true" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/tweets"
```

### 不下载视频

```bash
# 只下载图片，跳过视频
gallery-dl -o "videos=false" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"
```

### 搜索与高级搜索

```bash
# 搜索话题标签（最新结果）
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/hashtag/art"

# 高级搜索：从某用户且包含特定关键词
gallery-dl --cookies ~/twitter-cookies.txt "https://x.com/search?q=from:USERNAME+filter:media"

# 搜索热门结果
gallery-dl -o "search-results=top" --cookies ~/twitter-cookies.txt "https://x.com/search?q=KEYWORD"
```

### 一次导出全部内容

```bash
# 一次性导出用户信息、头像、时间线、媒体、点赞等所有内容
gallery-dl -o "include=all" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME"
```

### 断点续传

```bash
# 中断时会打印 cursor 值，下次从断点继续
gallery-dl -o "cursor=上次中断时打印的cursor值" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"
```

### 自定义文件命名

```bash
# 按日期和推文ID组织文件
gallery-dl -o "directory={date:%Y-%m}/{tweet_id}" --cookies ~/twitter-cookies.txt "https://x.com/USERNAME/media"
```

---

## 5. 完整配置文件示例

```json
{
    "extractor": {
        "twitter": {
            "cookies": "~/twitter-cookies.txt",
            "limit": 50,
            "retweets": false,
            "replies": true,
            "pinned": false,
            "quoted": false,
            "videos": true,
            "text-tweets": false,
            "cards": false,
            "unique": true,
            "cursor": true,
            "transform": true,
            "search-results": "latest",
            "ratelimit": "wait"
        }
    },
    "downloader": {
        "rate": "2M",
        "retries": 3,
        "timeout": 30
    },
    "output": {
        "mode": "terminal",
        "log": "[{name}][{levelname}] {message}",
        "log-level": "info"
    }
}
```

将此文件保存为 `~/.config/gallery-dl/config.json`（Linux/macOS）或 `%APPDATA%\gallery-dl\config.json`（Windows）。

---

## 6. 注意事项

1. **auth_token 是核心**：只需 `auth_token` 这一个 Cookie 即可完成认证。`ct0`（CSRF token）会自动处理。

2. **速率限制**：Twitter/X 有严格的 API 速率限制。默认配置 `ratelimit: "wait"` 会在遇到限制时自动等待。如果频繁触发限制，建议适当等待后继续。

3. **游客模式**：不提供 Cookies 也可以访问部分公开内容，但功能受限（如无法访问点赞、书签等）。

4. **账号安全**：Cookies 特别是 `auth_token` 等同于账号密码，**切勿分享 `cookies.txt` 文件**，建议在配置文件中使用 `~` 路径引用。

5. **下载数量没有硬性上限**：gallery-dl 会持续翻页直到没有更多内容或遇到限制。如需控制总量，可通过 `limit` 参数调整每次请求量，或手动中断（Ctrl+C）——配合 `cursor` 配置可实现断点续传。

6. **纯文本推文默认被忽略**：因为 gallery-dl 是媒体下载工具。如需文本内容，设置 `text-tweets: true` 并配合 `--exec` 后处理器自行处理文本。

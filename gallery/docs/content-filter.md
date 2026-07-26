# 内容过滤配置

**只下载用户自己的原创推文，跳过转发、引用、回复他人的内容。**

## 配置文件

`config.json` → `extractor.twitter`

## 参数说明

| 参数 | 类型 | 默认值 | 作用 |
|------|------|--------|------|
| `retweets` | bool | `false` | `false` 跳过所有转推（retweet），只保留原创 |
| `replies` | bool / `"self"` | `true` | `false` 跳过所有回复；`"self"` 只保留回复自己的 |
| `quoted` | bool | `false` | `false` 跳过引用推文（quote tweet） |

## 只下载原创内容（推荐）

```json
{
  "extractor": {
    "twitter": {
      "retweets": false,
      "replies": "self",
      "quoted": false
    }
  }
}
```

这三个参数都设为最严格模式时，只会下载用户自己发布的原创推文（含自回复）。

## 过滤逻辑

gallery-dl 在遍历推文列表时逐条判断（`twitter.py`）：

- **retweets** — 检查 `retweeted_status_id_str` 字段，存在即为转推，跳过
- **replies** — 检查 `in_reply_to_user_id_str` 字段，存在即为回复；`"self"` 模式下只保留 `user_id == in_reply_to_user_id` 的推文
- **quoted** — 检查 `quoted_by_id_str` 字段，存在即为引用推文，跳过

## 相关文件

- 配置文件：`gallery/config.json`
- 提取器源码：`.venv/lib/python3.14/site-packages/gallery_dl/extractor/twitter.py`

---
name: arxiv-daily-report
description: 追踪科研前沿方向并生成中文日报（Word 格式）。从 arXiv 按可配置的方向（计算机视觉前沿、水产+计算机视觉、医学+计算机视觉等）定向抓取最新论文，生成论文列表+摘要的中文日报 .docx。适用于"科研日报""论文追踪""前沿动态""arXiv 抓取"等请求。
---

# arXiv 科研前沿日报

按用户配置的方向从 arXiv 定向抓取最新论文，生成中文日报。用户要求生成科研日报、追踪论文前沿时，必须实际执行抓取并产出报告文件，不得只给出示例或教程。

按需加载的参考文件：
- `references/topics.json`：方向配置（分类、关键词、时间窗口、抓取量），**用户要调整抓取方向时修改此文件**
- `references/fetch_arxiv.py`：抓取脚本，零第三方依赖，直接运行
- `references/md_to_docx.py`：日报 Markdown 转 Word 脚本，依赖 python-docx，**必须用 `py -3` 运行**（python-docx 只装在 Windows Python 3.13 中）

## 生成日报流程

1. 执行抓取（在 skill 目录下）：

   ```bash
   python 科研前沿日报skill/references/fetch_arxiv.py
   ```

   默认抓取最近 3 天的论文（覆盖 arXiv 周末不更新的间隔），自动排除此前日报已覆盖的论文，输出 `reports/raw-YYYYMMDD.json`。

2. 读取输出 JSON，为每个方向撰写中文日报，先保存为 Markdown 中间稿 `reports/YYYYMMDD.md`，格式：

   ```markdown
   # 科研前沿日报 YYYY-MM-DD

   ## 方向一：计算机视觉前沿

   ### 1. 标题的中文译名
   - 原文标题：...
   - 作者：...（超过 5 人时列前 3 人加 et al.）
   - 链接：https://arxiv.org/abs/xxxx.xxxxx
   - 提交日期：YYYY-MM-DD
   - 摘要：中文概括（3-5 句，说明问题、方法、结果，不逐句翻译）
   ```

   - Markdown 稿只使用 `#`/`##`/`###` 标题、`- ` 列表项和普通段落，不使用表格、图片等其他语法（保证转 Word 不失真）
   - 某方向无新增论文时，该方向下写「本窗口期无新增论文」，不省略方向
   - 某方向抓取失败（JSON 中有 `error` 字段）时如实写明失败原因
   - 关键词误命中、与方向明显无关的论文（如无关领域论文碰巧含关键词）可剔除，并在该方向末尾注明剔除数量
   - 日报只基于抓取到的 JSON 数据撰写，不得虚构论文或补充抓取之外的内容

3. 转换为 Word（最终交付物为 .docx）：

   ```bash
   py -3 科研前沿日报skill/references/md_to_docx.py 科研前沿日报skill/reports/YYYYMMDD.md
   ```

   生成 `reports/YYYYMMDD.docx`。转换后必须验证：用 python-docx 读回文件，确认标题数与 Markdown 稿的 `##`/`###` 条目数一致。转换失败时先检查是否用了 `py -3`（而非 `python`）运行。

4. 向用户简要汇报：各方向新增篇数、Word 报告文件路径（.md 为中间稿，可保留备查）。

## 调整抓取方向

用户要求增删方向、改关键词、改时间窗口时，编辑 `references/topics.json`：

- `categories`：arXiv 分类，如 `cs.CV`（计算机视觉）、`eess.IV`（图像视频处理）、`cs.LG`（机器学习）、`q-bio`（定量生物）
- `keywords`：在标题/摘要全文中匹配的关键词，英文、空格分词匹配；含空格的短语按短语匹配；留空 `[]` 表示该分类下全部论文
- `days`：时间窗口（天），日报建议 3
- `max_results_per_topic`：每个方向最多抓取的条数

修改配置后应实际运行一次脚本验证新方向能抓到结果，并向用户展示各方向命中数量；命中为 0 时提示用户放宽关键词或分类。

## 注意事项

- arXiv 新论文在美东时间周日至周四晚间公布（北京时间周二至周六上午），周一和周日的日报新增可能很少，属正常现象
- 脚本已内置请求间隔（≥3 秒），不要并发调用 arXiv API
- 去重记录保存在 `reports/.seen_ids.json`，删除该文件后重新运行会重复覆盖旧论文；需要完整回顾时用 `--no-dedup` 并加大 `--days`
- 抓取失败多为网络问题，先重试一次；仍失败则按流程如实记录，不得编造论文填充日报

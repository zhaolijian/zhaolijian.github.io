# 作品与记录（个人站源码）

个人作品与记录的静态站点。线上地址：<https://zhaolijian.github.io>

## 目录结构

```
site/
├─ build.py                 构建脚本（无框架，生成静态 HTML 到 _site/）
├─ requirements.txt         构建依赖（markdown）
├─ src/
│  ├─ base.html             页面骨架（head / 页头 / 页脚，含 {{title}} 等占位符）
│  └─ pages/
│     ├─ index.html         首页（含 <!--THINKING_PREVIEW--> 等占位符）
│     ├─ thinking.html      思考列表外壳
│     ├─ reading.html       读书列表外壳
│     ├─ research.html      研究列表外壳
│     └─ cases/*.html       四个作品案例页
├─ content/                 ← 日常更新只改这里
│  ├─ thinking/*.md         思考文章
│  ├─ research/*.md         研究长文（kind: longread）与研究卡片（kind: card）
│  ├─ research/cards.json   旧版研究卡片数据
│  └─ reading/books.json    读书条目；books-new.json 会合并进列表
├─ assets/                  样式、脚本、图片
└─ .github/workflows/pages.yml  GitHub Actions：push 后自动构建并发布 Pages
```

## 新增一篇文章（不用本地环境）

1. 打开 GitHub 仓库，进入 `content/thinking/`，点「Add file → Create new file」；
2. 文件名用小写英文/拼音，例如 `growth-loops.md`；
3. 文件开头写 front matter，然后写正文（Markdown）：

```markdown
---
title: 标题
date: 2026-11
tags: 标签1, 标签2
summary: 40-60 字摘要，会显示在列表页。
source: 素材：个人笔记（可选，显示在文末）
links:
  - 参考链接标签｜https://example.com
---

正文从这里开始。可以用 ## 小标题、列表、引用。
```

4. 提交（Commit changes）。GitHub Actions 会自动构建并发布，约 1 分钟生效。
   - 列表页、首页预览、sitemap 都会自动更新，不需要改别处。

**研究长文**：放到 `content/research/`，front matter 用 `kind: longread` + `topic`，会自动生成带目录的长文页并列入研究页。
**研究卡片**：`kind: card`，另填 `data`（数据口径）与 `judgment`（判断），可选 `related: 长文文件名` 链接到长文。
**读书**：编辑 `content/reading/books.json`（结构见文件内示例，按分组组织）。

## 本地预览 / 手动构建

```bash
pip install -r requirements.txt          # 只为构建安装 markdown
python3 build.py                         # 生成 _site/
python3 build.py --serve                 # 生成并本地预览 http://127.0.0.1:8777
```

本地如果不想装依赖，可把 markdown 装到 `tools/pylibs`（已被 .gitignore 忽略），然后：

```bash
PYTHONPATH=tools/pylibs python3 build.py --serve
```

## 发布方式

- `main` 分支 = 源码；GitHub Pages 使用 **GitHub Actions** 部署（构建产物不进仓库）。
- push 到 `main` 后，`.github/workflows/pages.yml` 自动安装依赖、构建 `_site/`、部署到 Pages。
- 手动触发：仓库 Actions 页面 → "Build and deploy site" → Run workflow。

## 内容约定

- 不写个人身份信息（姓名、学校、公司、联系方式、简历）。
- 第三方数据只做结论级转述，标注「机构 + 时间 + 口径」；核不到写「待核对」。
- 不搬运第三方报告原文与图表；引用书只做观点转述。

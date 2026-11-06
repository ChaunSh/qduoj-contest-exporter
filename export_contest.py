from __future__ import annotations

import base64
import getpass
import hashlib
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from playwright.sync_api import sync_playwright

PROFILE = Path.home() / '.qduoj-export-browser'


class ProblemConverter(MarkdownConverter):
    def convert_sup(self, el, text, *args, **kwargs):
        return '<sup>' + text + '</sup>'

    def convert_sub(self, el, text, *args, **kwargs):
        return '<sub>' + text + '</sub>'


def clean_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', str(name)).strip(' .')
    name = name[:100] or 'contest'
    if re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', name, re.I):
        name = '_' + name
    return name


def contest_address(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password:
        raise ValueError('请输入完整的 http(s) 竞赛网址')
    # Vue history mode and hash mode are both common.
    m = re.search(r'(?:^|/)contest/(\d+)(?:/|$|\?)', p.path + '/' + p.fragment)
    if not m:
        raise ValueError('无法从网址识别竞赛 ID（应包含 /contest/数字）')
    return f'{p.scheme}://{p.netloc}', m.group(1)


def api(request, origin, path, **kwargs):
    response = request.get(origin + '/api/' + path, **kwargs)
    if not response.ok:
        raise RuntimeError(f'接口 {path} 返回 HTTP {response.status}')
    try:
        result = response.json()
    except Exception as e:
        raise RuntimeError(f'接口 {path} 未返回 JSON，学校可能修改了接口') from e
    if not isinstance(result, dict) or 'error' not in result:
        raise RuntimeError(f'接口 {path} 返回格式异常')
    if result['error'] is not None:
        raise RuntimeError(str(result.get('data')))
    return result.get('data')


def save_image(src, origin, request, folder, cache, failures):
    if src in cache:
        return cache[src]
    try:
        if src.startswith('data:'):
            match = re.fullmatch(r'data:(image/[\w.+-]+);base64,(.*)', src, re.S)
            if not match:
                raise ValueError('不支持的 data 图片格式')
            data = base64.b64decode(match.group(2), validate=True)
            ext = mimetypes.guess_extension(match.group(1)) or '.img'
        else:
            url = urljoin(origin + '/', src)
            if urlsplit(url).scheme not in ('http', 'https'):
                raise ValueError('不支持的图片地址')
            resp = request.get(url, timeout=30000)
            if not resp.ok:
                raise ValueError(f'HTTP {resp.status}')
            content_type = resp.headers.get('content-type', '').split(';')[0].strip().lower()
            if not content_type.startswith('image/'):
                raise ValueError(f'返回内容不是图片（{content_type}）')
            data = resp.body()
            ext = Path(unquote(urlsplit(url).path)).suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,6}', ext):
                ext = mimetypes.guess_extension(content_type) or '.img'
        if not data:
            raise ValueError('图片为空')
        filename = hashlib.sha256(src.encode()).hexdigest()[:20] + ext
        (folder / 'images').mkdir(exist_ok=True)
        (folder / 'images' / filename).write_bytes(data)
        cache[src] = 'images/' + filename
        return cache[src]
    except Exception as e:
        failures.append(f'{src}: {e}')
        return src


def convert_html(raw, origin, request, folder, cache, failures):
    soup = BeautifulSoup(str(raw or ''), 'html.parser')
    for img in soup.find_all('img'):
        if img.get('src'):
            img['src'] = save_image(img['src'], origin, request, folder, cache, failures)
    # Markdownify leaves text's LaTeX characters untouched with escaping disabled.
    return ProblemConverter(heading_style='ATX', escape_asterisks=False,
                            escape_underscores=False, escape_misc=False).convert(str(soup)).strip()


def fenced(value):
    value = str(value if value is not None else '')
    longest = max((len(x) for x in re.findall(r'`+', value)), default=0)
    fence = '`' * max(3, longest + 1)
    return fence + '\n' + value + ('' if value.endswith('\n') else '\n') + fence


def export(contest, problems, origin, request, folder):
    lines = ['# ' + str(contest.get('title') or 'Contest'), '']
    failures, cache = [], {}
    for p in problems:
        if not isinstance(p, dict) or not all(k in p for k in ('title', 'description', 'input_description', 'output_description', 'samples')):
            raise RuntimeError('题目数据缺少必要字段，可能无权查看或学校修改了接口')
        lines += [f"## {p.get('_id', '')} {p['title']}", '']
        meta = []
        if p.get('time_limit') is not None:
            meta.append(f"时间限制：{p['time_limit']} ms")
        if p.get('memory_limit') is not None:
            meta.append(f"内存限制：{p['memory_limit']} MB")
        if meta:
            lines += ['；'.join(meta), '']
        io_mode = p.get('io_mode')
        if isinstance(io_mode, dict) and (io_mode.get('input') or io_mode.get('output')):
            lines += [f"输入文件：{io_mode.get('input') or '-'}；输出文件：{io_mode.get('output') or '-'}", '']
        for field, label in [('description', '题目描述'), ('input_description', '输入'), ('output_description', '输出')]:
            lines += ['### ' + label, '', convert_html(p[field], origin, request, folder, cache, failures), '']
        for i, sample in enumerate(p['samples'], 1):
            lines += [f'### 样例 {i}', '', '输入：', '', fenced(sample.get('input')), '', '输出：', '', fenced(sample.get('output')), '']
        if p.get('hint'):
            lines += ['### 提示', '', convert_html(p['hint'], origin, request, folder, cache, failures), '']
        if p.get('source'):
            lines += ['来源：' + str(p['source']), '']
        lines += ['---', '']
    target = folder / (clean_name(contest.get('title') or 'contest') + '.md')
    target.write_text('\n'.join(lines), encoding='utf-8')
    return target, failures


def main():
    url = input('请输入比赛网址：').strip()
    origin, contest_id = contest_address(url)
    password = getpass.getpass('请输入比赛密码（无密码直接回车）：')
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(PROFILE), channel='msedge', headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(origin, wait_until='domcontentloaded', timeout=60000)
            request = context.request
            if not api(request, origin, 'profile'):
                print('请在打开的浏览器中登录 OJ。')
                input('登录完成后，在此处按回车继续...')
                if not api(request, origin, 'profile'):
                    raise RuntimeError('未检测到登录，请确认已在浏览器中成功登录')
            else:
                print('已检测到登录状态。')
            contest = api(request, origin, 'contest', params={'id': contest_id})
            if not isinstance(contest, dict):
                raise RuntimeError('比赛信息格式异常')
            if password:
                cookies = context.cookies(origin)
                csrf = next((x['value'] for x in cookies if x['name'] == 'csrftoken'), '')
                response = request.post(origin + '/api/contest/password', data={'contest_id': int(contest_id), 'password': password}, headers={'X-CSRFToken': csrf, 'Referer': origin + '/'})
                if not response.ok:
                    raise RuntimeError(f'比赛密码验证失败：HTTP {response.status}')
                result = response.json()
                if result.get('error') is not None:
                    raise RuntimeError('比赛密码验证失败：' + str(result.get('data')))
            problems = api(request, origin, 'contest/problem', params={'contest_id': contest_id})
            if not isinstance(problems, list):
                raise RuntimeError('题目列表格式异常，学校可能修改了接口')
            if not problems:
                raise RuntimeError('比赛未返回题目；请检查比赛是否已开始及当前账号权限')
            folder = Path.cwd() / (clean_name(contest.get('title') or 'contest') + '_' + contest_id)
            folder.mkdir(exist_ok=True)
            target, failures = export(contest, problems, origin, request, folder)
            print(f'已导出 {len(problems)} 道题：{target}')
            if failures:
                print('以下图片下载失败，Markdown 保留原地址：', file=sys.stderr)
                for fail in failures:
                    print('  ' + fail, file=sys.stderr)
                return 1
            return 0
        finally:
            context.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(f'导出失败：{exc}', file=sys.stderr)
        sys.exit(1)

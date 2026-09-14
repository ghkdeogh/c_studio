"""Read-only script/brief views. Content is shown as text, never executed."""
import re

def load_story(p,contract):
    brief=p/'BRIEF.md'
    requested=contract.get('script_file','shooting-script.md')
    script=(p/requested).resolve()
    if not script.is_relative_to(p.resolve()):raise ValueError('script_file escapes project')
    brief_text=brief.read_text(encoding='utf-8-sig') if brief.exists() else ''
    script_text=script.read_text(encoding='utf-8-sig') if script.is_file() else ''
    rows={}
    for line in script_text.splitlines():
        if not line.startswith('|'):continue
        cols=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(cols)!=5:continue
        m=re.match(r'^([0-9]+[A-Za-z0-9-]*)\s',cols[0])
        if m:rows[m[1]]={'target':cols[1],'dialogue':cols[2],'action':cols[3],'camera':cols[4]}
    return {'brief':brief_text,'script':script_text,'script_file':requested if script.is_file() else None,'rows':rows}

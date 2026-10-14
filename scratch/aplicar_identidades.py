from pathlib import Path
import re
projects=[(Path('C:/Mega/Proyect/Nucleus'),'Nucleus','Entel'),(Path('C:/Mega/Proyect/Modus'),'Modus','Integratel'),(Path('C:/Mega/Proyect/Opus'),'Opus','Claro')]
def icon(name,color):
 if name=='Nucleus':
  return f'<path d="M44 8A27 27 0 1 0 44 56" fill="none" stroke="{color}" stroke-width="10"/><circle cx="29" cy="32" r="8" fill="{color}"/><ellipse cx="32" cy="32" rx="32" ry="9" transform="rotate(-28 32 32)" fill="none" stroke="{color}" stroke-width="2.5"/>'
 if name=='Modus':
  return '<rect width="64" height="64" rx="15" fill="#173E76"/><path d="M16 48V17l16 16 16-16v31" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>'
 return f'<rect x="2" y="2" width="60" height="60" rx="14" fill="none" stroke="{color}" stroke-width="3.5"/><circle cx="32" cy="32" r="20" fill="none" stroke="{color}" stroke-width="3"/><path d="M32 12v8M52 32h-8M32 52v-8M12 32h8" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
def svg(name,operator,dark):
 fg='#F2F5FA' if dark else '#181818';blue='#91B9F3' if dark else '#173E76'
 content=f'<g transform="translate(45 3) scale(.72)">{icon(name,blue)}</g><text x="101" y="38" fill="{blue if name=="Nucleus" else fg}" font-size="32" font-weight="700">{name}</text><path d="M140 66l20 20M160 66l-20 20" stroke="{blue}" stroke-width="2.8" stroke-linecap="round"/>'
 if operator=='Integratel':
  content+=f'<text x="150" y="137" text-anchor="middle" fill="{fg}" font-size="40" font-weight="700" letter-spacing="-1.6">Integratel</text>'
 elif operator=='Entel':
  eb='#397CFF' if dark else '#0752EB'
  content+=f'<text x="58" y="141" fill="{eb}" font-size="66" font-weight="800">e</text><path d="M100 106Q117 123 100 141" fill="none" stroke="#FF6514" stroke-width="10" stroke-linecap="round"/><text x="125" y="139" fill="{eb}" font-size="46" font-weight="700" letter-spacing="-1.5">entel</text>'
 else:
  content+='<circle cx="150" cy="126" r="29" fill="#E50914"/><text x="149" y="135" text-anchor="middle" fill="#fff" font-size="21" font-weight="600" letter-spacing="-1">Claro</text><path d="M165 109v-7M173 112l5-5M176 119h7" stroke="#fff" stroke-width="2.7"/>'
 return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 160" role="img"><title>{name} × {operator}</title><g font-family="Inter,Arial,Helvetica,sans-serif">{content}</g></svg>'
css='''/* Identidades aprobadas: plataforma × operador. */
.brand-lockup{display:flex;align-items:center;justify-content:center;text-decoration:none;flex-shrink:0}
.brand-lockup img{display:block;object-fit:contain;flex-shrink:0}
.brand-lockup__light,.brand-lockup__dark{width:100%;height:auto}
.brand-lockup__dark,.brand-lockup__symbol{display:none!important}
body.dark-mode .brand-lockup__light{display:none!important}
body.dark-mode .brand-lockup__dark{display:block!important}
body .vl-logo.brand-lockup .brand-lockup__light{display:none!important}
body .vl-logo.brand-lockup .brand-lockup__dark{display:block!important}
body.light .vl-logo.brand-lockup .brand-lockup__light{display:block!important}
body.light .vl-logo.brand-lockup .brand-lockup__dark{display:none!important}
body .vl-logo.brand-lockup{width:285px;max-width:85vw;gap:0;margin-bottom:22px}
body.theme-vercel .sidebar-logo.brand-lockup{padding:10px 16px!important;gap:0;min-height:120px;box-sizing:border-box;overflow:hidden}
body .sidebar-logo.brand-lockup .brand-lockup__light,body .sidebar-logo.brand-lockup .brand-lockup__dark{width:100%;max-width:208px;height:auto}
body.sidebar-collapsed .sidebar-logo.brand-lockup{padding:14px 8px!important;min-height:60px}
body.sidebar-collapsed .sidebar-logo.brand-lockup .brand-lockup__light,body.sidebar-collapsed .sidebar-logo.brand-lockup .brand-lockup__dark{display:none!important}
body.sidebar-collapsed .sidebar-logo.brand-lockup .brand-lockup__symbol{display:block!important;width:30px;height:30px}
@media(max-width:600px){body .vl-logo.brand-lockup{width:230px;margin-bottom:18px}}
'''
for root,name,operator in projects:
 images=root/'static/img';images.mkdir(exist_ok=True)
 for dark in (False,True):
  (images/('brand-lockup-'+('dark' if dark else 'light')+'.svg')).write_text(svg(name,operator,dark),encoding='utf-8')
 (images/'brand-symbol.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'+icon(name,'#397CFF')+'</svg>',encoding='utf-8')
 (root/'static/css/brand-lockup.css').write_text(css,encoding='utf-8')
 include=f'''<a href="/" class="{{{{ 'sidebar-logo' if brand_location == 'sidebar' else 'vl-logo' }}}} brand-lockup" aria-label="{name} × {operator} · Inicio" title="{name} × {operator}">
    <img class="brand-lockup__light" src="/static/img/brand-lockup-light.svg?v=1" width="300" height="160" alt="" decoding="async">
    <img class="brand-lockup__dark" src="/static/img/brand-lockup-dark.svg?v=1" width="300" height="160" alt="" decoding="async">
    <img class="brand-lockup__symbol" src="/static/img/brand-symbol.svg?v=1" width="30" height="30" alt="" decoding="async">
</a>
'''
 (root/'templates/_brand_lockup.html').write_text(include,encoding='utf-8')
 for filename,location in [('base.html','sidebar'),('login.html','login')]:
  p=root/'templates'/filename;s=p.read_text(encoding='utf-8')
  pattern=r'<a href="/" class="'+('sidebar-logo' if location=='sidebar' else 'vl-logo')+r'".*?</a>'
  replacement="{% set brand_location = '"+location+"' %}{% include '_brand_lockup.html' %}"
  s,n=re.subn(pattern,lambda m:replacement,s,count=1,flags=re.S)
  assert n==1,(name,filename)
  s=s.replace('</head>','    <link rel="stylesheet" href="/static/css/brand-lockup.css?v=1">\n</head>',1)
  # Favicon uses the same platform symbol.
  s=re.sub(r'<link rel="icon"[^>]+>','<link rel="icon" type="image/svg+xml" href="/static/img/brand-symbol.svg?v=1">',s,count=1)
  p.write_text(s,encoding='utf-8')
 print(name+' × '+operator+' aplicado')

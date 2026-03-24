import re

with open('admin-ui/src/components/ProjectConfig.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

replacements = [
    ('p-8 space-y-6 animate-in slide-in-from-bottom-4 duration-300', 'p-5 space-y-4 animate-in slide-in-from-bottom-4 duration-300'),
    ('text-lg font-black text-gray-900 uppercase tracking-tight flex items-center gap-3', 'text-base font-black text-gray-900 uppercase tracking-tight flex items-center gap-2'),
    ('border-b border-gray-50 pb-4', 'border-b border-gray-50 pb-3'),
]

for old, new in replacements:
    c = c.replace(old, new)

for icon in ['Cpu', 'FolderGit2', 'Database', 'BookOpen']:
    c = c.replace(f'{icon} size={{20}}', f'{icon} size={{18}}')

c = c.replace('Trash2 size={18}', 'Trash2 size={16}')

c = c.replace('gap-5">\n                      <div>', 'gap-3">\n                      <div>')
c = c.replace('mb-2 block">', 'mb-1 block">')

c = c.replace('p-3 bg-gray-50 border border-gray-100 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none transition-all"', 'p-2.5 bg-gray-50 border border-gray-100 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-none transition-all"')

c = c.replace('min-h-20 p-3', 'min-h-16 p-2.5')
c = c.replace('min-h-28 p-3', 'min-h-20 p-2.5')
c = c.replace('gap-4 pt-6 border-t border-gray-50', 'gap-3 pt-4 border-t border-gray-50')
c = c.replace('py-4 bg-white border-2 border-gray-100', 'py-3 bg-white border-2 border-gray-100')
c = c.replace('py-4 rounded-2xl font-black', 'py-3 rounded-2xl font-black')

with open('admin-ui/src/components/ProjectConfig.tsx', 'w', encoding='utf-8') as f:
    f.write(c)

print('Done')

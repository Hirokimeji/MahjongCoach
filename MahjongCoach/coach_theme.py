"""Local ttk theme for the coaching window. Image borders stretch only in the middle."""
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

BG, CARD, HEADER, BLUSH = '#f7f1ee', '#fffcfa', '#f2e1df', '#f7e9ec'
TEXT, MUTED, ROSE = '#402f3b', '#725f69', '#9c4267'
FONT = 'Microsoft YaHei UI'


def install(window):
    style = ttk.Style(window)
    style.theme_use('clam')
    images = []

    def shape(fill, outside, width=32, height=32, radius=13, outline=None, switch=None):
        scale = 4
        image = Image.new('RGB', (width * scale, height * scale), outside)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, image.width-1, image.height-1), radius * scale,
                               fill=fill, outline=outline, width=2 * scale)
        if switch is not None:
            x = width-height if switch else 0
            draw.ellipse(((x+3)*scale, 3*scale, (x+height-3)*scale-1, (height-3)*scale-1), fill='white')
        photo = ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS), master=window)
        images.append(photo)
        return photo

    for name, color in [('Header', HEADER), ('Paper', CARD), ('Blush', BLUSH)]:
        surface = name + '.surface'
        style.element_create(surface, 'image', shape(color, BG), border=14, padding=0, sticky='nsew')
        style.layout(name+'.TFrame', [(surface, {'sticky': 'nsew'})])

    for name, outside, base, hover, pressed, fg in [
        ('Primary', HEADER, ROSE, '#883655', '#722b47', 'white'),
        ('Quiet', BG, '#eee3e3', '#e6d5d9', '#dec7cf', TEXT),
        ('Mode', BG, '#eee3e3', '#e6d5d9', '#dec7cf', TEXT),
    ]:
        states = [('disabled', shape('#eee6e5', outside))]
        if name == 'Mode':
            states.extend([('selected', 'focus', shape(ROSE, outside, outline='#6c2948')),
                           ('selected', shape(ROSE, outside))])
        states.extend([('pressed', shape(pressed, outside)),
                       ('focus', shape(hover, outside, outline='#b66b87')),
                       ('active', shape(hover, outside))])
        surface = name + '.surfaceButton'
        style.element_create(surface, 'image', shape(base, outside), *states, border=14, padding=0, sticky='nsew')
        key = name+'.TButton'
        style.layout(key, [(surface, {'sticky':'nsew', 'children':[
            ('Button.padding', {'sticky':'nsew', 'children':[('Button.label', {'sticky':'nsew'})]})]})])
        style.configure(key, font=(FONT, 10, 'bold' if name != 'Quiet' else 'normal'),
                        foreground=fg, anchor='center', padding=(14, 7), width=0)
        style.map(key, foreground=[('disabled', '#83747b'), ('selected', 'white')])

    switch = 'Pin.switch'
    def knob(on, focused=False):
        return shape(ROSE if on else '#ae9fa5', BG, 30, 17, 9,
                     '#77445c' if focused else None, switch=on)
    style.element_create(switch, 'image', knob(False), ('selected','focus',knob(True,True)),
                         ('selected',knob(True)), ('focus',knob(False,True)), sticky='')
    style.layout('Pin.TCheckbutton', [(switch, {'side':'left', 'sticky':''}), ('Checkbutton.padding', {
        'side':'left', 'children':[('Checkbutton.label', {'sticky':'w'})]})])
    style.configure('Pin.TCheckbutton', background=BG, foreground=TEXT, font=(FONT, 9), padding=(5, 4))

    style.element_create('Rose.trough', 'image', shape(BG, BG, 9, 18, 4), border=4, padding=0, sticky='nsew')
    style.element_create('Rose.thumb', 'image', shape('#caaeb9', BG, 9, 20, 4),
                         ('pressed', shape(ROSE, BG, 9, 20, 4)), ('active', shape('#b28a9a', BG, 9, 20, 4)),
                         border=4, padding=0, sticky='nsew')
    style.layout('Rose.Vertical.TScrollbar', [('Rose.trough', {'sticky':'nsew', 'children':[
        ('Rose.thumb', {'sticky':'nswe'})]})])
    return images

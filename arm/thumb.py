
from __future__ import absolute_import

from arm.arm import ARM, Register


class Thumb(ARM):
    stack = []

    @staticmethod
    def sign(value, bits):
        opp = 1 << bits
        if value & (opp >> 1):
            value -= opp
        return value

    def get_args4(self, left=False):
        args = [self.get_var(self.get_reg(idx), left) for idx in xrange(4)]
        if 0 and left:
            for arg in args:
                arg.persist = True
        return args

    def parse_next(self):
        """Read the next command and return the split values for logic operation
        """
        cmd = self.read_value(2)
        if cmd & 0b1111000000000000 == 0b0000000000000000:
            # lsl/lsr
            # TODO: asr: & 0b1110000000000000
            oper = (cmd >> 11) & 0x3
            val = (cmd >> 6) & 0x1F
            if oper == 0:
                oper = '>>'
            elif oper == 1:
                oper = '<<'
            src = self.get_var(self.get_reg(cmd & 0x7))
            dest = self.get_var(self.get_reg((cmd >> 3) & 0x7), left=True)
            return [self.assign(dest, self.statement(oper, src, val))]
        elif cmd & 0b1111100000000000 == 0b0001100000000000:
            # add/sub
            src_slot = (cmd >> 3) & 0x7
            if cmd & 0x400:
                val = (cmd >> 6) & 7
            else:
                val = self.get_var(self.get_reg((cmd >> 6) & 0x7))
            if cmd & 0x200:
                oper = '-'
            else:
                oper = '+'
                if isinstance(val, int) and not val and\
                        src_slot in self.registers:
                    self.registers[cmd & 0x7] = \
                        self.registers[src_slot]
                    return []
                    return [self.assign(self.registers[src_slot],
                                        self.registers[src_slot])]
            src = self.get_var(self.get_reg(src_slot))
            dest = self.get_var(self.get_reg(cmd & 0x7), left=True)
            return [self.assign(dest, self.statement(oper, src, val))]
            # TODO: cspr
        elif cmd & 0b1110000000000000 == 0b0010000000000000:
            # add/sub/cmp/mov immediate
            oper = (cmd >> 11) & 3
            reg = self.get_reg((cmd >> 8) & 0x7)
            val = cmd & 0xFF
            if oper == 0:
                # mov
                return [self.assign(self.get_var(reg, left=True), val)]
            elif oper == 1:
                # TODO: cmp
                oper = '~'
            elif oper == 2:
                oper = '+'
            elif oper == 3:
                oper = '-'
            src = self.get_var(reg)
            dest = self.get_var(reg, left=True)
            return [self.assign(dest, self.statement(oper, src, val))]
        elif cmd & 0b1111011000000000 == 0b1011010000000000:
            regs = self.get_regs(cmd & 0x7F)
            if cmd & 0x800:
                func = 'pop'
                if cmd & 0x100:
                    regs.append(Register(Register.SLOT_PC))
                for reg in regs[::-1]:
                    var = self.stack.pop()
                    if var is not None:
                        self.registers[reg.slot] = var
                    else:
                        self.registers.pop(reg.slot, None)
                if cmd & 0x100:
                    return [self.end(*[self.get_var(self.get_reg(idx))
                                       for idx in xrange(4)])]
                    # (all regs not popped but used)
            else:
                func = 'push'
                if cmd & 0x100:
                    regs.append(Register(Register.SLOT_LR))
                for reg in regs:
                    self.stack.append(self.registers.pop(reg.slot, None))
                    self.get_var(reg)
            return []
            # return [self.func(func, *regs)]
        elif cmd & 0b1111100000000000 == 0b1110000000000000:
            # b
            self.seek(self.tell()+(cmd & 0x3FF))
            return [self.noop()]
        elif cmd & 0b1111000000000000 == 0b1111000000000000:
            # bl
            ofs = (cmd & 0x7FF) << 12
            ofs += (self.read_value(2) & 0x7FF) << 1
            ofs = self.sign(ofs, 23) + self.tell()
            return [self.func('funcs.func_{0:x}'.format(ofs), *self.get_args4())]
            return [self.assign(self.get_args4(True),
                                self.func('funcs.func_{0:x}'.format(ofs),
                                          *self.get_args4()))]
            return [self.func('bl', ofs,
                              *[self.get_var(self.get_reg(idx))
                                for idx in xrange(4)])]
        elif cmd & 0b1111111100000000 == 0b0100011100000000:
            # bx
            reg = self.get_reg((cmd >> 3) & 0x7, cmd & 0x40)
            if reg.slot == Register.SLOT_LR:
                return [self.end()]
            return [self.func('bx', reg)]
        elif cmd & 0b1111100000000000 == 0b0100100000000000:
            # ldr dest [pc, #v]
            pass
        elif cmd & 0b1111001000000000 == 0b0101000000000000:
            # ldr/str Rd [Rb, Ro]
            if cmd & 0x400:
                size = 'byte'
            else:
                size = 'word'
            ofs = self.get_reg((cmd >> 6) & 7)
            base = self.get_var(self.get_reg((cmd >> 3) & 7))
            dest = self.get_var(self.get_reg(cmd & 7), left=True)
            if cmd & 0x800:
                func = 'get'  # ldr
                return [self.assign(dest, self.func(
                    'ram.get_{0}'.format(size), self.add(base, ofs), level=0))]
            else:
                func = 'set'  # str
                return [self.func('ram.set_{0}'.format(size),
                                  self.add(base, ofs), dest)]
        elif cmd & 0b1110000000000000 == 0b0110000000000000 or\
                cmd & 0b1111000000000000 == 0b1000000000000000:
            # ldr/str Rd [Rb, #ofs]
            ofs = (cmd >> 6) & 0x1F
            base = self.get_var(self.get_reg((cmd >> 3) & 7))
            dest = self.get_var(self.get_reg(cmd & 7), left=True)
            if cmd & 0x8000:
                size = 'halfword'
            elif cmd & 0x1000:
                size = 'byte'
            else:
                size = 'word'
                ofs <<= 2
            if cmd & 0x800:
                func = 'get'  # ldr
                return [self.assign(dest, self.func(
                    'ram.get_{0}'.format(size), self.add(base, ofs), level=0))]
            else:
                func = 'set'  # str
                return [self.func('ram.set_{0}'.format(size),
                                  self.add(base, ofs), dest)]
        return [self.unknown(cmd, 2)]

    def prepare(self):
        for idx in xrange(4):
            self.get_var(self.get_reg(idx))
        self.registers[0].name = 'state'
        return []

    def simplify_x(self, parsed):
        reparsed = []
        for expr in parsed:
            # recurse
            try:
                subexpr = expr.expression
            except:
                pass
            else:
                expr.expression, = self.simplify([subexpr])
            try:
                args = expr.args
            except:
                pass
            else:
                newargs = []
                expr.args = [self.simplify([arg])[0] for arg in args]
            # remove +0, *1, <<0 ,etc.
            try:
                oper = expr.operator
                args = expr.args
            except:
                pass
            else:
                if oper in ('+', '-', '<<', '>>'):
                    args = [arg for arg in args if arg != 0]
                elif oper in ('*', ):
                    args = [arg for arg in args if arg != 1]
                if len(args) == 1:
                    reparsed.append(args[0])
                    continue
            reparsed.append(expr)
        return reparsed
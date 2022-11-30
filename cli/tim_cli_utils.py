import sys
from functools import partial, wraps
from copy import deepcopy
import builtins as __builtin__
import subprocess

ACTIONS = {}  # Populated with the `@register_action` decorator


def _parser():
    raise Exception(
        "_parser() method mus be globaly overwritten! user set_parser(function)")


def set_parser(parser):
    global _parser
    _parser = parser


def _dispatch_register_action_decorator(f, name=None, cont: bool = False, call=None, alias: list = [], silent=False, parse_own_args=False):
    ACTIONS.update({name if name else f.__name__: {
        "alias": alias,
        "continue": cont,
        "func": f,
        "exec": call if call else lambda a: f(a),
        "silent": silent,
        "parse_own_args": parse_own_args
    }})

    @wraps(f)
    def run(*args, **kwargs):
        return f(*args, **kwargs)
    return run


def register_action(**kwargs):
    return partial(_dispatch_register_action_decorator, **kwargs)


def _action_by_alias(alias):
    for act in ACTIONS:
        if alias in [*ACTIONS[act]["alias"], act]:
            return act, ACTIONS[act]
    else:
        raise Exception(f"Action or alias '{alias}' not found")


@register_action(name="help", alias=["h", "?"])
def _print_help(a):
    # print(main.__doc__)
    _parser().print_help()
    print("Generating action help messages...")
    for act in ACTIONS:
        print(
            f"action '{act}' (with aliases {', '.join(ACTIONS[act]['alias'])})")
        f = ACTIONS[act].get("func", None)
        if f:
            info = ACTIONS[act]['func'].__doc__
            print(f"\tinfo: {info}\n")
        else:
            print("\tNo info availabol")


@register_action(alias=["only_print", "stdout", "%%"], cont=True)
def _print_commands(args, extra_out=["C"]):
    """
    overwrites subprocess.run to only output the commands 
    """
    def _print_command_and_args(*args, **kwargs):
        print(
            *extra_out, f"_cmd: `{' '.join(args[0]) if isinstance(args[0], list) else args[0]}`, kwargs: {kwargs}")
    subprocess.run = _print_command_and_args
    subprocess.check_output = _print_command_and_args
    subprocess.call = _print_command_and_args


@register_action(alias=["non_verbose", "low_out", "null"], cont=True)
def _non_verbose(args, silence_subprocess=True, use_w=True, use_c=True, use_o=True):
    """ Reduced output and wraps tags in args to actual strings """
    # TODO Convert in some general logging
    if not args.silent:
        print("WARNING: This also hides subrpocess output")
    if silence_subprocess:
        _print_commands(args, extra_out="")

    def __only_print_lvl(*args, **kwargs):
        _args = list(args)
        if "W" in _args and use_w:
            _args.remove('W')
            return __builtin__.print(*['WARNING:', *_args], **kwargs)
        if "C" in _args and use_c:
            _args.remove('C')  # Then this is a command print
            return __builtin__.print(*['cmd:', *_args], **kwargs)
        if "O" in _args and use_o:
            _args.remove('O')  # Then this is a command print
            return __builtin__.print(*['cmd:', *_args], **kwargs)
        # Other things are not printed
    globals()["print"] = __only_print_lvl


def parse_actions_run():
    """
    This is a very convenient commandline utility based on argparse 
    You can write any function in a script that usees this
    add the @register_action(...) decoratior and the function will be run on
    `./run.py <action-name>`
    then the action can claim to parse the unrecognized cli args via `args.unknown`
    """
    a, _ = _parser().parse_known_args()
    assert getattr(a, "actions") and a.actions
    reparse = (None, False)
    # Check if there is a 'parse_own_args' action in the actions
    for action in a.actions:
        try:
            act, action_meta = _action_by_alias(action)
        except:
            continue
        if action_meta["parse_own_args"]:
            # In this case we need to repase args with a delimeter
            reparse = (action, True)
    if reparse[1]:
        assert isinstance(reparse[0], str)
        _partial = sys.argv[1:sys.argv.index(reparse[0])+1]
        a = _parser().parse_args(_partial)
        setattr(a, 'unknown', sys.argv[sys.argv.index(reparse[0]) + 1:])
    else:
        a = _parser().parse_args()
        setattr(a, 'unknown', [])

    silence_all_actions = a.silent if a.silent else False
    setattr(a, "silent", silence_all_actions)
    if silence_all_actions:
        _non_verbose(a, silence_subprocess=False, use_c=False, use_w=False)
    # `unknown` args are parsed again in the end,
    # if they where not passed by any of the actions
    # this allowes invidual actions to parse their own args, e.g.: see _eksctl
    for action in a.actions if isinstance(a.actions, list) else [a.actions]:
        k, _action = _action_by_alias(action)
        if not _action["silent"]:
            print(f"Performing '{k}' -action")
        else:
            # Disables all output exept of warnings and commands
            a.silent = True
        _action["exec"](a)
        if not _action.get("continue", False) and not a.silent:
            print(f"Ran into final action '{k}'")
            break
    if len(a.unknown) > 1:
        print("there where unhandled extra args: " + " ".join(a.unknown))
    if not a.silent:
        print("Exiting 'run.py' cli...")

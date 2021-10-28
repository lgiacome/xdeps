from dataclasses import dataclass, field
import logging

from .refs import ARef, Ref, ObjectAttrRef
from .refs import AttrRef, CallRef, ItemRef
from .utils import os_display_png, AttrDict
from .sorting import toposort

logger=logging.getLogger(__name__)

class FuncWrapper:
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        return CallRef(self.func, args, tuple(kwargs.items()))


class Task:
    pass

class GenericTask(Task):
    taskid: object
    action: object
    targets: object
    dependencies: tuple

    def __repr__(self):
        return f"<Task {self.taskid}:{self.dependencies}=>{self.targets}>"

    def run(self,*args):
        logger.info(f"Run {self}")
        return self.action(*args)


class ExprTask(Task):
    def __init__(self,target,expr):
        self.taskid=target
        self.targets=set([target])
        self.dependencies=expr._get_dependencies()
        self.expr=expr

    def __repr__(self):
        return f"{self.taskid} = {self.expr}"

    def run(self):
        value=self.expr._get_value()
        for target in self.targets:
            target._set_value(value)

class InheritanceTask(Task):
    def __init__(self,children,parents):
        self.taskid=children
        self.targets=set([children])
        self.dependencies=set(parents)

    def __repr__(self):
        return f"{self.taskid} <- {self.parents}"

    def run(self,event):
        key,value,isattr=event
        for target in self.targets:
            if isattr:
              getattr(target,key)._set_value(value)
            else:
              target[key]._set_value(value)


class DepEnv:
    __slots__=('_data','_')
    def __init__(self,data,ref):
        object.__setattr__(self,'_data',data)
        object.__setattr__(self,'_',ref)

    def __getattr__(self,key):
        return getattr(self._data,key)

    def __getitem__(self,key):
        return self._data[key]

    def __setattr__(self,key,value):
        self._[key]=value

    def __setitem__(self,key,value):
        self._[key]=value

    def _eval(self,expr):
        return self._._eval(expr)

class DepManager:
    def __init__(self):
        self.tasks= {}
        self.rdeps = {}
        self.rtask ={}
        self.containers={}

    def ref(self,container=None,label='_'):
        if container is None:
            container=AttrDict()
        objref=Ref(container,self,label)
        assert label not in self.containers
        self.containers[label]=objref
        return objref

    def refattr(self,container=None,label='_'):
        if container is None:
            container=AttrDict()
        return ObjectAttrRef(container,self,label)

    def set_value(self, ref, value):
        logger.info(f"set_value {ref} {value}")
        redef=False
        if ref in self.tasks:
            self.unregister(ref)
            redef=True
        if isinstance(value,ARef): # value is an expression
            self.register(ref,ExprTask(ref,value))
            if redef:
                value=value._get_value() # to be updated
        ref._set_value(value)
        self.run_tasks(self.find_tasks(ref._get_dependencies()))

    def run_tasks(self,tasks):
        for task in tasks:
            logger.info(f"Run {task}")
            task.run()

    def del_value(self,ref):
        self.unregister(ref)

    def register(self,taskid,task):
        self.tasks[taskid]=task
        for dep in task.dependencies:
            self.rdeps.setdefault(dep,set()).update(task.targets)

    def unregister(self,taskid):
        task=self.tasks[taskid]
        for dep in task.dependencies:
            for target in task.targets:
              self.rdeps[dep].remove(target)
        del self.tasks[taskid]

    def find_deps(self,start):
        assert type(start) in (list,tuple,set)
        deps=toposort(self.rdeps,start)
        return deps

    def find_tasks(self,start):
        deps=self.find_deps(start)
        tasks=[self.tasks[d] for d in deps if d in self.tasks]
        return tasks

    def gen_fun(self,name,**kwargs):
        varlist,start=list(zip(*kwargs.items()))
        tasks=self.find_tasks(start)
        fdef=[f"def {name}({','.join(varlist)}):"]
        for vname,vref in kwargs.items():
            fdef.append(f"  {vref} = {vname}")
        for tt in tasks:
            fdef.append(f"  {tt}")
        fdef="\n".join(fdef)

        gbl={}
        lcl={}
        gbl.update((k, r._owner) for k,r in self.containers.items())
        exec(fdef,gbl,lcl)
        return lcl[name]

    def to_pydot(self,start):
        from pydot import Dot, Node, Edge
        pdot = Dot("g", graph_type="digraph",rankdir="LR")
        for task in self.find_tasks(start):
            tn=Node(str(task.taskid), shape="circle")
            pdot.add_node(tn)
            for tt in task.targets:
                pdot.add_node(Node(str(tt), shape="square"))
                pdot.add_edge(Edge(tn, str(tt), color="blue"))
            for tt in task.dependencies:
                pdot.add_node(Node(str(tt), shape="square"))
                pdot.add_edge(Edge(str(tt),tn, color="blue"))
        os_display_png(pdot.create_png())
        return pdot

    def env(self,label='_',data=None):
        if data is None:
            data=AttrDict()
        ref=self.ref(data,label=label)
        return DepEnv(data,ref)

manager=DepManager()
// callgraph_basic.sv
// 函数调用图基础测试

package cg_pkg;

  // 1. 基础调用链
  class basic_seq;
    rand bit [7:0] data;

    task body();
      do_init();
      do_send();
    endtask

    task do_init();
      data = 8'h00;
    endtask

    task do_send();
      void'(randomize());
    endtask
  endclass

  // 2. 继承 + super 调用
  class ext_seq extends basic_seq;
    rand bit [3:0] tag;

    task body();
      super.body();
      do_tag();
    endtask

    task do_tag();
      void'(randomize());
    endtask
  endclass

  // 3. fork/join
  class fork_seq;
    rand bit [7:0] a;
    rand bit [7:0] b;

    task body();
      fork
        task_a();
        task_b();
      join_any
    endtask

    task task_a();
      void'(randomize());
    endtask

    task task_b();
      void'(randomize());
    endtask
  endclass

  // 4. fork...join_none
  class fork_none_seq;
    task body();
      fork
        do_bg();
      join_none
    endtask

    task do_bg();
    endtask
  endclass

  // 5. new() 构造
  class my_driver;
    ext_seq seq;

    task run_phase();
      seq = new();
      seq.body();
    endtask
  endclass

  // 6. 函数调用函数
  class func_cls;
    function int compute(int a, int b);
      return add(a, b) * 2;
    endfunction

    function int add(int a, int b);
      return a + b;
    endfunction
  endclass

  // 7. 多层调用
  class multi_level;
    task run();
      level1();
    endtask

    task level1();
      level2();
    endtask

    task level2();
      void'(randomize());
    endtask
  endclass

endpackage

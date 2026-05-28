// uvm_testbench.sv
// UVM testbench 静态结构测试
// 使用最小 stub 避免 UVM 库依赖

package uvm_tb_pkg;

  // ============================================================
  // UVM 最小 stub
  // ============================================================
  virtual class uvm_object;
    function new(string name = "");
    endfunction
  endclass

  virtual class uvm_component extends uvm_object;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_sequence_item extends uvm_object;
    function new(string name = "");
    endfunction
  endclass

  virtual class uvm_sequence #(type REQ = uvm_sequence_item) extends uvm_object;
    function new(string name = "");
    endfunction
  endclass

  virtual class uvm_driver #(type REQ = uvm_sequence_item, type RSP = uvm_sequence_item) extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_monitor extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_scoreboard extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_agent extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_env extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_test extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  // ============================================================
  // Sequence Item
  // ============================================================
  class my_transaction extends uvm_sequence_item;
    rand bit [7:0] data;
    rand bit [3:0] addr;

    function new(string name = "");
      super.new(name);
    endfunction
  endclass

  // ============================================================
  // Sequences
  // ============================================================
  class base_sequence extends uvm_sequence #(my_transaction);
    function new(string name = "");
      super.new(name);
    endfunction

    virtual task body();
      my_transaction tx;
      tx = new();
      void'(tx.randomize());
    endtask
  endclass

  class write_sequence extends base_sequence;
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      super.body();
    endtask
  endclass

  class read_sequence extends base_sequence;
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      super.body();
    endtask
  endclass

  // ============================================================
  // Driver
  // ============================================================
  class my_driver extends uvm_driver #(my_transaction);
    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    task run_phase();
      forever begin
        my_transaction tx;
        tx = new();
        void'(tx.randomize());
      end
    endtask
  endclass

  // ============================================================
  // Monitor
  // ============================================================
  class my_monitor extends uvm_monitor;
    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    task run_phase();
      forever begin
        // sample
      end
    endtask
  endclass

  // ============================================================
  // Scoreboard
  // ============================================================
  class my_scoreboard extends uvm_scoreboard;
    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    task run_phase();
      forever begin
        // compare
      end
    endtask
  endclass

  // ============================================================
  // Agent
  // ============================================================
  class my_agent extends uvm_agent;
    my_driver    drv;
    my_monitor   mon;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      drv = new("drv", this);
      mon = new("mon", this);
    endfunction
  endclass

  // ============================================================
  // Env
  // ============================================================
  class my_env extends uvm_env;
    my_agent     agent;
    my_scoreboard sb;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      agent = new("agent", this);
      sb = new("sb", this);
    endfunction
  endclass

  // ============================================================
  // Test
  // ============================================================
  class my_test extends uvm_test;
    my_env env;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      env = new("env", this);
    endfunction

    task run_phase();
      write_sequence wr_seq;
      read_sequence  rd_seq;
      wr_seq = new();
      rd_seq = new();
    endtask
  endclass

endpackage

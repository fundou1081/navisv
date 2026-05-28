// uvm_complex.sv
// 复杂 UVM testbench - port connection + scoreboard

package uvm_complex_pkg;

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

  // TLM port stubs
  class uvm_analysis_port #(type T = int) extends uvm_object;
    function new(string name = "");
    endfunction
    function void connect(uvm_object provider);
    endfunction
  endclass

  class uvm_analysis_imp #(type T = int, type IMP = int) extends uvm_object;
    function new(string name = "");
    endfunction
  endclass

  class uvm_blocking_put_port #(type T = int) extends uvm_object;
    function new(string name = "");
    endfunction
    function void connect(uvm_object provider);
    endfunction
  endclass

  class uvm_blocking_get_port #(type T = int) extends uvm_object;
    function new(string name = "");
    endfunction
    function void connect(uvm_object provider);
    endfunction
  endclass

  // ============================================================
  // Transaction
  // ============================================================
  class axi_transaction extends uvm_sequence_item;
    rand bit [31:0] addr;
    rand bit [31:0] data;
    rand bit [3:0]  burst_len;
    rand bit        is_write;

    function new(string name = "");
      super.new(name);
    endfunction
  endclass

  class wb_transaction extends uvm_sequence_item;
    rand bit [15:0] wb_addr;
    rand bit [31:0] wb_data;
    rand bit        wb_we;

    function new(string name = "");
      super.new(name);
    endfunction
  endclass

  // ============================================================
  // Sequences
  // ============================================================
  class axi_base_sequence extends uvm_sequence #(axi_transaction);
    function new(string name = "");
      super.new(name);
    endfunction

    virtual task body();
      axi_transaction tx;
      tx = new();
      void'(tx.randomize());
    endtask
  endclass

  class axi_write_sequence extends axi_base_sequence;
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      super.body();
    endtask
  endclass

  class axi_read_sequence extends axi_base_sequence;
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      super.body();
    endtask
  endclass

  class axi_burst_sequence extends axi_base_sequence;
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      super.body();
    endtask
  endclass

  class wb_sequence extends uvm_sequence #(wb_transaction);
    function new(string name = "");
      super.new(name);
    endfunction

    task body();
      wb_transaction tx;
      tx = new();
      void'(tx.randomize());
    endtask
  endclass

  // ============================================================
  // AXI Monitor (有 analysis_port)
  // ============================================================
  class axi_monitor extends uvm_monitor;
    uvm_analysis_port #(axi_transaction) ap;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap");
    endfunction

    task run_phase();
      forever begin
        axi_transaction tx;
        tx = new();
        void'(tx.randomize());
      end
    endtask
  endclass

  // ============================================================
  // WB Monitor (有 analysis_port)
  // ============================================================
  class wb_monitor extends uvm_monitor;
    uvm_analysis_port #(wb_transaction) ap;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
      ap = new("ap");
    endfunction

    task run_phase();
      forever begin
        wb_transaction tx;
        tx = new();
        void'(tx.randomize());
      end
    endtask
  endclass

  // ============================================================
  // AXI Driver
  // ============================================================
  class axi_driver extends uvm_driver #(axi_transaction);
    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    task run_phase();
      forever begin
        axi_transaction tx;
        tx = new();
        void'(tx.randomize());
      end
    endtask
  endclass

  // ============================================================
  // WB Driver
  // ============================================================
  class wb_driver extends uvm_driver #(wb_transaction);
    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    task run_phase();
      forever begin
        wb_transaction tx;
        tx = new();
        void'(tx.randomize());
      end
    endtask
  endclass

  // ============================================================
  // Scoreboard (有 analysis_imp)
  // ============================================================
  class axi_scoreboard extends uvm_scoreboard;
    uvm_analysis_imp #(axi_transaction, axi_scoreboard) axi_imp;
    uvm_analysis_imp #(wb_transaction, axi_scoreboard) wb_imp;

    axi_transaction axi_queue[$];
    wb_transaction  wb_queue[$];

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
      axi_imp = new("axi_imp");
      wb_imp = new("wb_imp");
    endfunction

    function void write_axi(axi_transaction tx);
      axi_queue.push_back(tx);
    endfunction

    function void write_wb(wb_transaction tx);
      wb_queue.push_back(tx);
    endfunction

    task run_phase();
      forever begin
        // compare
      end
    endtask
  endclass

  // ============================================================
  // Coverage Collector (有 analysis_imp)
  // ============================================================
  class coverage_collector extends uvm_component;
    uvm_analysis_imp #(axi_transaction, coverage_collector) imp;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
      imp = new("imp");
    endfunction

    function void write(axi_transaction tx);
      // sample coverage
    endfunction
  endclass

  // ============================================================
  // AXI Agent
  // ============================================================
  class axi_agent extends uvm_agent;
    axi_driver   drv;
    axi_monitor  mon;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      drv = new("drv", this);
      mon = new("mon", this);
    endfunction
  endclass

  // ============================================================
  // WB Agent
  // ============================================================
  class wb_agent extends uvm_agent;
    wb_driver   drv;
    wb_monitor  mon;

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
    axi_agent         axi_agt;
    wb_agent          wb_agt;
    axi_scoreboard    sb;
    coverage_collector cov;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      axi_agt = new("axi_agt", this);
      wb_agt  = new("wb_agt", this);
      sb      = new("sb", this);
      cov     = new("cov", this);
    endfunction

    function void connect_phase();
      // Port connections
      axi_agt.mon.ap.connect(sb.axi_imp);
      wb_agt.mon.ap.connect(sb.wb_imp);
      axi_agt.mon.ap.connect(cov.imp);
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
      axi_write_sequence wr_seq;
      axi_read_sequence  rd_seq;
      axi_burst_sequence burst_seq;
      wb_sequence        wb_seq;
      wr_seq = new();
      rd_seq = new();
      burst_seq = new();
      wb_seq = new();
    endtask
  endclass

endpackage

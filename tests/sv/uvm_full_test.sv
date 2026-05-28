// uvm_full_test.sv
// 完整 UVM testbench - 覆盖更多真实模式

`include "uvm_macros.svh"
import uvm_pkg::*;

// ============================================================
// Transaction
// ============================================================
class axi_transaction extends uvm_sequence_item;
  rand bit [31:0] addr;
  rand bit [31:0] data;
  rand bit [3:0]  burst_len;
  rand bit        is_write;

  `uvm_object_utils_begin(axi_transaction)
    `uvm_field_int(addr, UVM_ALL_ON)
    `uvm_field_int(data, UVM_ALL_ON)
    `uvm_field_int(burst_len, UVM_ALL_ON)
    `uvm_field_int(is_write, UVM_ALL_ON)
  `uvm_object_utils_end

  function new(string name = "axi_transaction");
    super.new(name);
  endfunction

  constraint c_addr { addr[1:0] == 2'b00; }
  constraint c_burst { burst_len inside {[1:16]}; }
endclass

// ============================================================
// Sequences
// ============================================================
class base_sequence extends uvm_sequence #(axi_transaction);
  `uvm_object_utils(base_sequence)

  function new(string name = "base_sequence");
    super.new(name);
  endfunction

  virtual task body();
    axi_transaction tx;
    repeat(5) begin
      tx = axi_transaction::type_id::create("tx");
      start_item(tx);
      assert(tx.randomize());
      finish_item(tx);
    end
  endtask
endclass

class write_sequence extends base_sequence;
  `uvm_object_utils(write_sequence)

  function new(string name = "write_sequence");
    super.new(name);
  endfunction

  task body();
    axi_transaction tx;
    repeat(3) begin
      tx = axi_transaction::type_id::create("tx");
      start_item(tx);
      tx.is_write = 1;
      assert(tx.randomize() with { addr inside {[32'h1000:32'h2000]}; });
      finish_item(tx);
    end
  endtask
endclass

class read_sequence extends base_sequence;
  `uvm_object_utils(read_sequence)

  function new(string name = "read_sequence");
    super.new(name);
  endfunction

  task body();
    axi_transaction tx;
    repeat(3) begin
      tx = axi_transaction::type_id::create("tx");
      start_item(tx);
      tx.is_write = 0;
      assert(tx.randomize() with { addr inside {[32'h0000:32'h0FFF]}; });
      finish_item(tx);
    end
  endtask
endclass

class burst_sequence extends base_sequence;
  `uvm_object_utils(burst_sequence)

  function new(string name = "burst_sequence");
    super.new(name);
  endfunction

  task body();
    super.body();
  endtask
endclass

// ============================================================
// Driver
// ============================================================
class axi_driver extends uvm_driver #(axi_transaction);
  `uvm_component_utils(axi_driver)

  int max_retries;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    uvm_config_db#(int)::get(this, "", "max_retries", max_retries);
    if ($test$plusargs("VERBOSE"))
      `uvm_info("DRV", "Verbose mode enabled", UVM_LOW)
    void'($value$plusargs("RETRY=%d", max_retries));
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      axi_transaction tx;
      seq_item_port.get_next_item(tx);
      `uvm_info("DRV", $sformatf("Driving: addr=%0h data=%0h", tx.addr, tx.data), UVM_HIGH)
      seq_item_port.item_done();
    end
  endtask
endclass

// ============================================================
// Monitor
// ============================================================
class axi_monitor extends uvm_monitor;
  `uvm_component_utils(axi_monitor)

  uvm_analysis_port #(axi_transaction) ap;
  int sample_count;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    uvm_config_db#(int)::get(this, "", "sample_count", sample_count);
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      axi_transaction tx;
      tx = axi_transaction::type_id::create("tx");
      void'(tx.randomize());
      ap.write(tx);
    end
  endtask
endclass

// ============================================================
// Scoreboard
// ============================================================
class axi_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(axi_scoreboard)

  uvm_analysis_imp #(axi_transaction, axi_scoreboard) imp;
  axi_transaction expected_q[$];

  function new(string name, uvm_component parent);
    super.new(name, parent);
    imp = new("imp", this);
  endfunction

  function void write(axi_transaction t);
    `uvm_info("SCB", $sformatf("Received: addr=%0h", t.addr), UVM_HIGH)
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      #10;
    end
  endtask
endclass

// ============================================================
// Coverage
// ============================================================
class axi_coverage extends uvm_component;
  `uvm_component_utils(axi_coverage)

  uvm_analysis_imp #(axi_transaction, axi_coverage) imp;

  bit [31:0] cov_addr;
  bit [31:0] cov_data;
  bit        cov_is_write;

  covergroup cg_trans;
    cp_addr: coverpoint cov_addr {
      bins low  = {[0:32'h0FFF]};
      bins mid  = {[32'h1000:32'h1FFF]};
      bins high = {[32'h2000:32'hFFFF_FFFF]};
    }
    cp_data: coverpoint cov_data {
      bins zero = {0};
      bins lo   = {[1:32'hFFFF]};
      bins max  = {32'hFFFF_FFFF};
    }
    cp_write: coverpoint cov_is_write {
      bins read  = {0};
      bins write = {1};
    }
    cx_addr_write: cross cp_addr, cp_write;
  endgroup

  function new(string name, uvm_component parent);
    super.new(name, parent);
    imp = new("imp", this);
    cg_trans = new();
  endfunction

  function void write(axi_transaction t);
    cov_addr = t.addr;
    cov_data = t.data;
    cov_is_write = t.is_write;
    cg_trans.sample();
  endfunction
endclass

// ============================================================
// Agent
// ============================================================
class axi_agent extends uvm_agent;
  `uvm_component_utils(axi_agent)

  axi_driver   drv;
  axi_monitor  mon;
  uvm_sequencer #(axi_transaction) sqr;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    drv = axi_driver::type_id::create("drv", this);
    mon = axi_monitor::type_id::create("mon", this);
    sqr = uvm_sequencer#(axi_transaction)::type_id::create("sqr", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass

// ============================================================
// Env
// ============================================================
class my_env extends uvm_env;
  `uvm_component_utils(my_env)

  axi_agent      agt;
  axi_scoreboard sb;
  axi_coverage   cov;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    agt = axi_agent::type_id::create("agt", this);
    sb  = axi_scoreboard::type_id::create("sb", this);
    cov = axi_coverage::type_id::create("cov", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    agt.mon.ap.connect(sb.imp);
    agt.mon.ap.connect(cov.imp);
  endfunction
endclass

// ============================================================
// Test
// ============================================================
class base_test extends uvm_test;
  `uvm_component_utils(base_test)

  my_env env;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  string test_seq_name;

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    env = my_env::type_id::create("env", this);
    uvm_config_db#(int)::set(this, "env.agt.drv", "max_retries", 3);
    uvm_config_db#(int)::set(this, "env.agt.mon", "sample_count", 100);
    void'($value$plusargs("TEST_SEQ=%s", test_seq_name));
  endfunction

  task run_phase(uvm_phase phase);
    base_sequence seq;
    phase.raise_objection(this);
    seq = base_sequence::type_id::create("seq");
    seq.start(env.agt.sqr);
    #100;
    phase.drop_objection(this);
  endtask
endclass

class write_test extends base_test;
  `uvm_component_utils(write_test)

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  task run_phase(uvm_phase phase);
    write_sequence seq;
    phase.raise_objection(this);
    seq = write_sequence::type_id::create("seq");
    seq.start(env.agt.sqr);
    #100;
    phase.drop_objection(this);
  endtask
endclass

class read_test extends base_test;
  `uvm_component_utils(read_test)

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  task run_phase(uvm_phase phase);
    read_sequence seq;
    phase.raise_objection(this);
    seq = read_sequence::type_id::create("seq");
    seq.start(env.agt.sqr);
    #100;
    phase.drop_objection(this);
  endtask
endclass

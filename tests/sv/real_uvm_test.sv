// real_uvm_test.sv
// 使用真实 UVM 库的测试文件

`include "uvm_macros.svh"
import uvm_pkg::*;

// Transaction
class my_transaction extends uvm_sequence_item;
  rand bit [7:0] data;
  rand bit [3:0] addr;

  `uvm_object_utils_begin(my_transaction)
    `uvm_field_int(data, UVM_ALL_ON)
    `uvm_field_int(addr, UVM_ALL_ON)
  `uvm_object_utils_end

  function new(string name = "my_transaction");
    super.new(name);
  endfunction

  constraint c_data { data inside {[0:200]}; }
  constraint c_addr { addr < 4'hC; }
endclass

// Sequences
class base_seq extends uvm_sequence #(my_transaction);
  `uvm_object_utils(base_seq)

  function new(string name = "base_seq");
    super.new(name);
  endfunction

  virtual task body();
    my_transaction tx;
    repeat(3) begin
      tx = my_transaction::type_id::create("tx");
      start_item(tx);
      assert(tx.randomize());
      finish_item(tx);
    end
  endtask
endclass

class write_seq extends base_seq;
  `uvm_object_utils(write_seq)

  function new(string name = "write_seq");
    super.new(name);
  endfunction

  task body();
    super.body();
  endtask
endclass

class read_seq extends base_seq;
  `uvm_object_utils(read_seq)

  function new(string name = "read_seq");
    super.new(name);
  endfunction

  task body();
    super.body();
  endtask
endclass

// Driver
class my_driver extends uvm_driver #(my_transaction);
  `uvm_component_utils(my_driver)

  int baud_rate;
  bit [7:0] ctrl_reg;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    uvm_config_db#(int)::get(this, "", "baud_rate", baud_rate);
    uvm_config_db#(bit [7:0])::get(this, "", "ctrl_reg", ctrl_reg);
    if ($test$plusargs("DEBUG"))
      `uvm_info("DRV", "Debug mode", UVM_LOW)
    void'($value$plusargs("BAUD=%d", baud_rate));
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      my_transaction tx;
      seq_item_port.get_next_item(tx);
      `uvm_info("DRV", $sformatf("Driving: data=%0h addr=%0h", tx.data, tx.addr), UVM_LOW)
      seq_item_port.item_done();
    end
  endtask
endclass

// Monitor
class my_monitor extends uvm_monitor;
  `uvm_component_utils(my_monitor)

  uvm_analysis_port #(my_transaction) ap;
  int sample_rate;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    uvm_config_db#(int)::get(this, "", "sample_rate", sample_rate);
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      my_transaction tx;
      tx = my_transaction::type_id::create("tx");
      ap.write(tx);
      `uvm_info("MON", "Sampled transaction", UVM_HIGH)
    end
  endtask
endclass

// Scoreboard
class my_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(my_scoreboard)

  uvm_analysis_imp #(my_transaction, my_scoreboard) ap;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void write(my_transaction t);
    `uvm_info("SCB", $sformatf("Received: data=%0h", t.data), UVM_LOW)
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      #10;
    end
  endtask
endclass

// Agent
class my_agent extends uvm_agent;
  `uvm_component_utils(my_agent)

  my_driver    drv;
  my_monitor   mon;
  uvm_sequencer #(my_transaction) sqr;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    drv = my_driver::type_id::create("drv", this);
    mon = my_monitor::type_id::create("mon", this);
    sqr = uvm_sequencer#(my_transaction)::type_id::create("sqr", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass

// Env
class my_env extends uvm_env;
  `uvm_component_utils(my_env)

  my_agent      agt;
  my_scoreboard sb;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    agt = my_agent::type_id::create("agt", this);
    sb  = my_scoreboard::type_id::create("sb", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    agt.mon.ap.connect(sb.ap);
  endfunction
endclass

// Test
class my_test extends uvm_test;
  `uvm_component_utils(my_test)

  my_env env;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  string test_name;

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    env = my_env::type_id::create("env", this);
    uvm_config_db#(int)::set(this, "env.agt.drv", "baud_rate", 115200);
    uvm_config_db#(bit [7:0])::set(this, "env.agt.drv", "ctrl_reg", 8'hA5);
    uvm_config_db#(int)::set(this, "env.agt.mon", "sample_rate", 48000);
    void'($value$plusargs("TEST_NAME=%s", test_name));
  endfunction

  task run_phase(uvm_phase phase);
    base_seq seq;
    phase.raise_objection(this);
    seq = base_seq::type_id::create("seq");
    seq.start(env.agt.sqr);
    phase.drop_objection(this);
  endtask
endclass

// uvm_config_plusargs.sv
// config_db 配置流 + plusargs 测试

package uvm_cp_pkg;

  // UVM stub
  virtual class uvm_object;
    function new(string name = "");
    endfunction
  endclass

  virtual class uvm_component extends uvm_object;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_driver #(type REQ = int) extends uvm_component;
    function new(string name = "", uvm_component parent = null);
    endfunction
  endclass

  virtual class uvm_monitor extends uvm_component;
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

  // config_db stub
  class uvm_config_db #(type T = int);
    static function void set(uvm_component cntxt, string inst_name, string field_name, T value);
    endfunction
    static function bit get(uvm_component cntxt, string inst_name, string field_name, inout T value);
    endfunction
  endclass

  // ============================================================
  // 组件
  // ============================================================
  class my_driver extends uvm_driver #(int);
    int baud_rate;
    bit [7:0] ctrl_reg;
    string agent_name;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      // 从 config_db 获取配置
      uvm_config_db #(int)::get(this, "", "baud_rate", baud_rate);
      uvm_config_db #(bit [7:0])::get(this, "", "ctrl_reg", ctrl_reg);
      uvm_config_db #(string)::get(this, "", "agent_name", agent_name);

      // plusargs
      if ($test$plusargs("DEBUG"))
        $display("Debug mode enabled");

      void'($value$plusargs("BAUD=%d", baud_rate));
      void'($value$plusargs("CTRL=%h", ctrl_reg));
    endfunction
  endclass

  class my_monitor extends uvm_monitor;
    int sample_rate;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      uvm_config_db #(int)::get(this, "", "sample_rate", sample_rate);
    endfunction
  endclass

  class my_env extends uvm_env;
    my_driver   drv;
    my_monitor  mon;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      drv = new("drv", this);
      mon = new("mon", this);

      // 设置配置
      uvm_config_db #(int)::set(this, "drv", "baud_rate", 115200);
      uvm_config_db #(bit [7:0])::set(this, "drv", "ctrl_reg", 8'hA5);
      uvm_config_db #(string)::set(this, "drv", "agent_name", "my_agent");
      uvm_config_db #(int)::set(this, "mon", "sample_rate", 48000);
    endfunction
  endclass

  class my_test extends uvm_test;
    my_env env;

    function new(string name = "", uvm_component parent = null);
      super.new(name, parent);
    endfunction

    function void build_phase();
      int custom_baud;
      bit custom_baud_ok;
      env = new("env", this);

      // 测试级别的 config_db 设置
      uvm_config_db #(int)::set(this, "env.drv", "baud_rate", 9600);

      // plusargs 影响配置
      custom_baud_ok = $value$plusargs("CUSTOM_BAUD=%d", custom_baud);
      if (custom_baud_ok)
        uvm_config_db #(int)::set(this, "env.drv", "baud_rate", custom_baud);
    endfunction
  endclass

endpackage

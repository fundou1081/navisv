// ============================================================
// covergroup_basic.sv
// CoverGroup 解析基础测试
// ============================================================

module cg_basic (
  input  logic       clk,
  input  logic [7:0] data_in,
  input  logic [1:0] mode,
  input  logic       err,
  output logic [7:0] data_out
);

  // ----------------------------------------------------------
  // 1. 基础 covergroup: 单 coverpoint, 多 bins
  // ----------------------------------------------------------
  covergroup cg_basic_cg @(posedge clk);
    cp_data: coverpoint data_in {
      bins zero = {0};
      bins low  = {[1:64]};
      bins mid  = {[65:192]};
      bins high = {[193:255]};
    }
  endgroup

  // ----------------------------------------------------------
  // 2. illegal_bins 和 ignore_bins
  // ----------------------------------------------------------
  covergroup cg_bins_cg @(posedge clk);
    cp_data: coverpoint data_in {
      bins valid    = {[0:200]};
      illegal_bins overflow = {[201:255]};
      ignore_bins reserved  = {8'hFF};
    }
  endgroup

  // ----------------------------------------------------------
  // 3. 多 coverpoint
  // ----------------------------------------------------------
  covergroup cg_multi_cg @(posedge clk);
    cp_data: coverpoint data_in {
      bins range[] = {[0:255]};
    }
    cp_mode: coverpoint mode {
      bins idle   = {0};
      bins active = {1};
      bins error  = {2};
      bins debug  = {3};
    }
    cp_err: coverpoint err {
      bins no_err  = {0};
      bins has_err = {1};
    }
  endgroup

  // ----------------------------------------------------------
  // 4. cross 覆盖
  // ----------------------------------------------------------
  covergroup cg_cross_cg @(posedge clk);
    cp_mode: coverpoint mode {
      bins idle  = {0};
      bins run   = {1};
      bins err   = {2};
    }
    cp_err: coverpoint err {
      bins no  = {0};
      bins yes = {1};
    }
    cx_mode_err: cross cp_mode, cp_err;
  endgroup

  // ----------------------------------------------------------
  // 5. cross + 自定义 cross bins
  // ----------------------------------------------------------
  covergroup cg_cross_bins_cg @(posedge clk);
    cp_a: coverpoint data_in[7:4] {
      bins zero = {0};
      bins one  = {1};
    }
    cp_b: coverpoint data_in[3:0] {
      bins zero = {0};
      bins one  = {1};
    }
    cx_ab: cross cp_a, cp_b {
      bins a0_b0 = binsof(cp_a.zero) && binsof(cp_b.zero);
      illegal_bins a0_b1 = binsof(cp_a.zero) && binsof(cp_b.one);
    }
  endgroup

  // ----------------------------------------------------------
  // 6. wildcard bins
  // ----------------------------------------------------------
  covergroup cg_wildcard_cg @(posedge clk);
    cp_data: coverpoint data_in {
      wildcard bins even = {8'b???????0};
      wildcard bins odd  = {8'b???????1};
    }
  endgroup

  // ----------------------------------------------------------
  // 7. default bin
  // ----------------------------------------------------------
  covergroup cg_default_cg @(posedge clk);
    cp_data: coverpoint data_in {
      bins special = {0, 255};
      bins others  = default;
    }
  endgroup

  // ----------------------------------------------------------
  // 8. option
  // ----------------------------------------------------------
  covergroup cg_option_cg @(posedge clk);
    option.per_instance = 1;
    option.at_least = 2;
    cp_data: coverpoint data_in {
      option.at_least = 3;
      bins all = {[0:255]};
    }
  endgroup

  // ----------------------------------------------------------
  // 实例化
  // ----------------------------------------------------------
  cg_basic_cg     cg_basic_inst = new();
  cg_bins_cg      cg_bins_inst = new();
  cg_multi_cg     cg_multi_inst = new();
  cg_cross_cg     cg_cross_inst = new();
  cg_cross_bins_cg cg_cross_bins_inst = new();
  cg_wildcard_cg  cg_wildcard_inst = new();
  cg_default_cg   cg_default_inst = new();
  cg_option_cg    cg_option_inst = new();

endmodule

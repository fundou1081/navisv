// ============================================================
// covergroup_quality.sv
// coverage 质量评估测试
// ============================================================

package cg_quality_pkg;

  // ----------------------------------------------------------
  // 1. data 类信号: 好的 bin 策略
  // ----------------------------------------------------------
  class data_good_cls;
    rand bit [7:0] data;

    covergroup cg;
      cp_data: coverpoint data {
        bins zero    = {0};
        bins max     = {255};
        bins low     = {[1:64]};
        bins mid     = {[65:190]};
        bins high    = {[191:254]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 2. data 类信号: 差的 bin 策略 (缺极值)
  // ----------------------------------------------------------
  class data_bad_cls;
    rand bit [7:0] data;

    covergroup cg;
      cp_data: coverpoint data {
        bins lo = {[0:127]};
        bins hi = {[128:255]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 3. control 类信号: 好的策略 (有特殊值)
  // ----------------------------------------------------------
  class ctrl_good_cls;
    rand bit [1:0] state;

    covergroup cg;
      cp_state: coverpoint state {
        bins idle    = {0};
        bins active  = {1};
        bins error   = {2};
        bins debug   = {3};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 4. control 类信号: 差的策略 (缺特殊值)
  // ----------------------------------------------------------
  class ctrl_bad_cls;
    rand bit [1:0] state;

    covergroup cg;
      cp_state: coverpoint state {
        bins range = {[0:3]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 5. 好的 cross 覆盖
  // ----------------------------------------------------------
  class cross_good_cls;
    rand bit [1:0] mode;
    rand bit       err;

    covergroup cg;
      cp_mode: coverpoint mode {
        bins idle  = {0};
        bins run   = {1};
        bins halt  = {2};
      }
      cp_err: coverpoint err {
        bins no  = {0};
        bins yes = {1};
      }
      cx_mode_err: cross cp_mode, cp_err;
    endgroup
  endclass

  // ----------------------------------------------------------
  // 6. 缺少 cross 覆盖
  // ----------------------------------------------------------
  class cross_bad_cls;
    rand bit [1:0] mode;
    rand bit       err;

    covergroup cg;
      cp_mode: coverpoint mode {
        bins idle  = {0};
        bins run   = {1};
      }
      cp_err: coverpoint err {
        bins no  = {0};
        bins yes = {1};
      }
      // 没有 cross!
    endgroup
  endclass

endpackage

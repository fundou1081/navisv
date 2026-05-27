// ============================================================
// covergroup_constraint_check.sv
// bin-constraint 一致性检查测试
// ============================================================

package cg_check_pkg;

  // ----------------------------------------------------------
  // 1. 死 bin: constraint 排除了 bin 的取值
  // ----------------------------------------------------------
  class dead_bin_cls;
    rand bit [7:0] data;

    constraint c_data {
      data inside {[0:100]};  // 只允许 0-100
    }

    covergroup cg;
      cp_data: coverpoint data {
        bins low    = {[0:50]};
        bins mid    = {[51:100]};
        bins high   = {[101:200]};   // 死 bin! constraint 排除 101-200
        bins max    = {255};         // 死 bin! constraint 排除 255
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 2. 遗漏 bin: constraint 允许但没有 bin 覆盖
  // ----------------------------------------------------------
  class missing_bin_cls;
    rand bit [7:0] addr;

    constraint c_addr {
      addr inside {[0:255]};
    }

    covergroup cg;
      cp_addr: coverpoint addr {
        bins zero = {0};
        bins one  = {1};
        // 遗漏! 2-254 没有 bin 覆盖
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 3. missing illegal bin: constraint 禁止但没标 illegal
  // ----------------------------------------------------------
  class missing_illegal_cls;
    rand bit [7:0] val;

    constraint c_val {
      val inside {[0:100], [200:255]};  // 禁止 101-199
    }

    covergroup cg;
      cp_val: coverpoint val {
        bins lo = {[0:100]};
        bins hi = {[200:255]};
        // 遗漏! 101-199 应该标 illegal_bins
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 4. 完全一致: bin 和 constraint 范围匹配
  // ----------------------------------------------------------
  class consistent_cls;
    rand bit [7:0] data;

    constraint c_data {
      data inside {[0:63]};
    }

    covergroup cg;
      cp_data: coverpoint data {
        bins zero = {0};
        bins low  = {[1:32]};
        bins mid  = {[33:63]};
        illegal_bins overflow = {[64:255]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 5. 条件约束下的 bin 检查
  // ----------------------------------------------------------
  class conditional_cls;
    rand bit [7:0] mode;
    rand bit [7:0] data;

    constraint c_data {
      if (mode == 0) data inside {[0:127]};
      else           data inside {[128:255]};
    }

    covergroup cg;
      cp_data: coverpoint data {
        bins lo = {[0:127]};
        bins hi = {[128:255]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 6. 部分重叠: bin 范围与 constraint 部分重叠
  // ----------------------------------------------------------
  class partial_overlap_cls;
    rand bit [7:0] data;

    constraint c_data {
      data inside {[30:200]};
    }

    covergroup cg;
      cp_data: coverpoint data {
        bins low  = {[0:50]};    // 部分死 bin: 0-29 被 constraint 排除
        bins mid  = {[51:150]};  // 完全有效
        bins high = {[151:255]}; // 部分死 bin: 201-255 被 constraint 排除
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 7. 多 coverpoint 独立检查
  // ----------------------------------------------------------
  class multi_cp_cls;
    rand bit [7:0] a;
    rand bit [3:0] b;

    constraint c_a { a inside {[0:100]}; }
    constraint c_b { b inside {[0:8]}; }

    covergroup cg;
      cp_a: coverpoint a {
        bins range = {[0:100]};
        illegal_bins over = {[101:255]};
      }
      cp_b: coverpoint b {
        bins range = {[0:8]};
        bins high  = {[9:15]};  // 死 bin
      }
    endgroup
  endclass

endpackage

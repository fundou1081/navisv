// ============================================================
// constraint_conditional.sv
// navisv constraint graph 功能测试 - 条件约束 & 位精确度
// ============================================================

package constraint_conditional_pkg;

  // ----------------------------------------------------------
  // 1. 位精确度：部分位约束
  // ----------------------------------------------------------
  class bit_precision_packet;
    rand bit [15:0] ctrl_word;
    rand bit [7:0]  addr;
    rand bit [7:0]  data;

    // 全宽约束
    constraint c_addr_range {
      addr inside {[8'h00:8'hFF]};
    }

    // 部分位约束：只约束 ctrl_word 的高 4 位
    constraint c_ctrl_high {
      ctrl_word[15:12] inside {4'h1, 4'h2, 4'h3};
    }

    // 部分位约束：只约束 ctrl_word 的低 8 位
    constraint c_ctrl_low {
      ctrl_word[7:0] == addr;
    }

    // 单 bit 约束
    constraint c_ctrl_flag {
      ctrl_word[8] == 1'b1;
    }
  endclass

  // ----------------------------------------------------------
  // 2. 条件约束：if/else inside constraint
  // ----------------------------------------------------------
  class conditional_packet;
    rand bit [7:0] mode;
    rand bit [7:0] length;
    rand bit [7:0] payload[];
    rand bit [3:0] tag;

    // 简单 if/else
    constraint c_mode_len {
      if (mode == 8'h00) {
        length inside {[1:16]};
      } else if (mode == 8'h01) {
        length inside {[17:64]};
      } else {
        length inside {[65:255]};
      }
    }

    // 条件 + 跨变量约束
    constraint c_mode_tag {
      if (mode == 8'h00) {
        tag == 4'h0;
      } else {
        tag inside {[4'h1:4'hF]};
      }
    }

    // 无条件约束（作为对照）
    constraint c_always {
      payload.size() == length;
    }
  endclass

  // ----------------------------------------------------------
  // 3. 条件约束 + 继承
  // ----------------------------------------------------------
  class base_mode;
    rand bit [7:0] mode;
    rand bit [7:0] length;

    constraint c_base_mode {
      if (mode == 8'h00) {
        length inside {[1:32]};
      } else {
        length inside {[33:255]};
      }
    }
  endclass

  class ext_mode extends base_mode;
    rand bit [3:0] priority_level;

    // 覆盖父类的条件约束
    constraint c_ext_mode {
      if (mode == 8'h00) {
        length inside {[1:16]};
        priority_level == 4'h0;
      } else {
        length inside {[17:128]};
        priority_level inside {[4'h1:4'hF]};
      }
    }
  endclass

  // ----------------------------------------------------------
  // 4. 条件约束 + 组合
  // ----------------------------------------------------------
  class inner_cls;
    rand bit [7:0] value;
    rand bit [3:0] flag;

    constraint c_inner {
      if (flag == 4'h0) {
        value inside {[0:63]};
      } else {
        value inside {[64:255]};
      }
    }
  endclass

  class outer_cls;
    rand inner_cls inner;
    rand bit [7:0] selector;

    constraint c_outer_cond {
      if (selector == 8'hAA) {
        inner.flag == 4'h0;
      }
    }

    constraint c_outer_val {
      inner.value == selector;
    }
  endclass

  // ----------------------------------------------------------
  // 5. randc 和 soft 约束
  // ----------------------------------------------------------
  class randc_packet;
    randc bit [3:0] seq_num;
    rand  bit [7:0] data;

    constraint c_seq {
      soft data inside {[8'h00:8'h7F]};
    }
  endclass

endpackage

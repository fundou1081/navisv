// ============================================================
// constraint_basic.sv
// navisv constraint graph 功能测试 - 基础场景
// ============================================================

package constraint_basic_pkg;

  // ----------------------------------------------------------
  // 1. 基础类：单个 constraint，两个 rand 变量
  // ----------------------------------------------------------
  class simple_packet;
    rand bit [7:0] length;
    rand bit [7:0] data;

    constraint c_simple {
      length inside {[1:64]};
      data < length;
    }
  endclass

  // ----------------------------------------------------------
  // 2. 多层继承：3 层
  // ----------------------------------------------------------
  class base_packet;
    rand bit [7:0] length;
    rand bit [7:0] payload[];

    constraint c_base {
      length inside {[1:63]};
      payload.size() == length;
    }
  endclass

  class mid_packet extends base_packet;
    rand bit [3:0] tag;

    constraint c_mid {
      length inside {[16:63]};
      tag < 4'h8;
    }
  endclass

  class eth_packet extends mid_packet;
    rand bit [47:0] dst_mac;
    rand bit [47:0] src_mac;

    constraint c_eth_size {
      length inside {[46:63]};
    }

    constraint c_eth_mac {
      dst_mac != src_mac;
    }
  endclass

  // ----------------------------------------------------------
  // 3. 组合关系：单层
  // ----------------------------------------------------------
  class wrapper;
    rand eth_packet pkt;
    rand bit [7:0] header;
    rand bit [3:0] pri;

    constraint c_wrap_len {
      pkt.length == header;
    }

    constraint c_wrap_pri {
      pri < 4'h4;
      pkt.tag == pri;
    }
  endclass

  // ----------------------------------------------------------
  // 4. 深层组合：top_env -> wrapper -> eth_packet
  // ----------------------------------------------------------
  class top_env;
    rand wrapper wrp;
    rand bit [7:0] global_id;

    constraint c_top {
      wrp.header == global_id;
    }
  endclass

endpackage
